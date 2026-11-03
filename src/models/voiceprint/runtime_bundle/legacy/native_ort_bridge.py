"""Small ctypes adapter to the real ONNX Runtime C API (API v17).
No Python ORT wheel, Torch, graph interpreter, or native compilation is required.
Only dense numeric CPU tensors are supported; unsupported types fail explicitly.
All native execution stays inside the bundled, independently identified ORT library.
"""
from pathlib import Path
import ctypes as c
import hashlib
import json
import math
import platform
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent
NATIVE=HERE/'_native_ort'
P=c.c_void_p
PP=c.POINTER(P)
I=c.c_int
Z=c.c_size_t
I64=c.c_int64
CP=c.c_char_p
TYPES={1:np.dtype('float32'),2:np.dtype('uint8'),3:np.dtype('int8'),4:np.dtype('uint16'),
       5:np.dtype('int16'),6:np.dtype('int32'),7:np.dtype('int64'),9:np.dtype('bool'),
       10:np.dtype('float16'),11:np.dtype('float64'),12:np.dtype('uint32'),13:np.dtype('uint64')}
ENUMS={value:key for key,value in TYPES.items()}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def candidate_path():
    return NATIVE/'libonnxruntime.so.1.17.1'


def validate_native_files():
    metadata=json.loads((NATIVE/'manifest.json').read_text(encoding='utf-8'))
    for name,sha in metadata['files'].items():
        path=(NATIVE/name).resolve()
        if not path.is_relative_to(NATIVE.resolve()) or sha256(path)!=sha:
            raise ValueError('Native ORT package hash mismatch: '+name)
    return metadata


class API:
    def __init__(self,library,verify=True):
        self.library_path=str(Path(library).resolve())
        self.functions={}
        if verify:
            validate_native_files()
        self.indices=json.loads((NATIVE/'api_indices.json').read_text(encoding='utf-8'))['names']
        self.factory=c.WINFUNCTYPE if platform.system()=='Windows' else c.CFUNCTYPE
        loader=c.WinDLL if platform.system()=='Windows' else c.CDLL
        self.library=loader(self.library_path)
        class ApiBase(c.Structure):
            _fields_=[('GetApi',P),('GetVersionString',P)]
        self.library.OrtGetApiBase.restype=c.POINTER(ApiBase)
        self.library.OrtGetApiBase.argtypes=[]
        base=self.library.OrtGetApiBase().contents
        self.version=self.factory(CP)(base.GetVersionString)().decode('utf-8')
        table=self.factory(P,c.c_uint32)(base.GetApi)(17)
        if not table:
            raise RuntimeError('Native runtime does not expose C API 17')
        self.table=c.cast(table,c.POINTER(P))
        self.env=P();self.memory=P();self.allocator=P()
        self.call('CreateEnv',[I,CP,PP],2,b'SonicArm-CAPI',c.byref(self.env))
        self.call('DisableTelemetryEvents',[P],self.env)
        self.call('CreateCpuMemoryInfo',[I,I,PP],1,0,c.byref(self.memory))
        self.call('GetAllocatorWithDefaultOptions',[PP],c.byref(self.allocator))
        # Environment and CPU memory descriptor are process-wide and outlive every session.

    def function(self,name,restype,argtypes):
        key=(name,restype,tuple(argtypes))
        if key not in self.functions:
            address=self.table[self.indices[name]]
            if not address:
                raise RuntimeError('Null C API function: '+name)
            self.functions[key]=self.factory(restype,*argtypes)(address)
        return self.functions[key]

    def call(self,name,argtypes,*args):
        status=self.function(name,P,argtypes)(*args)
        if status:
            message=self.function('GetErrorMessage',CP,[P])(status).decode('utf-8',errors='replace')
            self.release('Status',status)
            raise RuntimeError('ONNX Runtime '+name+': '+message)

    def release(self,kind,pointer):
        if pointer:
            self.function('Release'+kind,None,[P])(pointer)

    def tensor_description(self,info):
        enum=I();ndim=Z()
        self.call('GetTensorElementType',[P,c.POINTER(I)],info,c.byref(enum))
        self.call('GetDimensionsCount',[P,c.POINTER(Z)],info,c.byref(ndim))
        if ndim.value>32:
            raise ValueError('Unreasonable tensor rank')
        dimensions=(I64*ndim.value)()
        symbols=(CP*ndim.value)()
        self.call('GetDimensions',[P,c.POINTER(I64),Z],info,dimensions,ndim.value)
        self.call('GetSymbolicDimensions',[P,c.POINTER(CP),Z],info,symbols,ndim.value)
        shape=[int(d) if d>=0 else (symbols[i].decode('utf-8') if symbols[i] else None)
               for i,d in enumerate(dimensions)]
        if enum.value not in TYPES:
            raise TypeError('Unsupported ONNX tensor element type '+str(enum.value))
        return TYPES[enum.value],shape


_API=None


def default_api():
    global _API
    if _API is None:
        if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):
            raise RuntimeError('Bundled native ORT is for ARMv7 Linux only')
        _API=API(candidate_path())
    return _API


class Session:
    """The minimal session interface used by this package's real model runner."""
    def __init__(self,path,threads=1,optimize=False,api=None):
        self.api=api or default_api()
        self.pointer=P();options=P()
        if threads<1:
            raise ValueError('Positive thread count required')
        a=self.api
        try:
            a.call('CreateSessionOptions',[PP],c.byref(options))
            a.call('SetIntraOpNumThreads',[P,I],options,threads)
            a.call('SetInterOpNumThreads',[P,I],options,1)
            a.call('SetSessionExecutionMode',[P,I],options,0)
            a.call('SetSessionGraphOptimizationLevel',[P,I],options,99 if optimize else 0)
            a.call('DisableCpuMemArena',[P],options)
            a.call('DisableMemPattern',[P],options)
            a.call('SetSessionLogSeverityLevel',[P,I],options,3)
            path_type=c.c_wchar_p if platform.system()=='Windows' else CP
            name=str(Path(path).resolve())
            if path_type==CP:
                name=name.encode('utf-8')
            a.call('CreateSession',[P,path_type,P,PP],a.env,name,options,c.byref(self.pointer))
            self.inputs=self._metadata('Input')
            self.outputs=self._metadata('Output')
        except Exception:
            self.close()
            raise
        finally:
            a.release('SessionOptions',options)

    def _metadata(self,kind):
        a=self.api;count=Z();result=[]
        a.call('SessionGet'+kind+'Count',[P,c.POINTER(Z)],self.pointer,c.byref(count))
        for index in range(count.value):
            name=P();type_info=P()
            try:
                a.call('SessionGet'+kind+'Name',[P,Z,P,PP],self.pointer,index,a.allocator,c.byref(name))
                decoded=c.string_at(name).decode('utf-8')
                a.call('SessionGet'+kind+'TypeInfo',[P,Z,PP],self.pointer,index,c.byref(type_info))
                tensor_info=P()
                a.call('CastTypeInfoToTensorInfo',[P,PP],type_info,c.byref(tensor_info))
                if not tensor_info:
                    raise TypeError('Only tensor graph interfaces are supported')
                dtype,shape=a.tensor_description(tensor_info)
                result.append(SimpleNamespace(name=decoded,shape=shape,dtype=dtype))
            finally:
                if name:
                    a.call('AllocatorFree',[P,P],a.allocator,name)
                a.release('TypeInfo',type_info)
        return result

    def get_inputs(self):
        return self.inputs

    def get_outputs(self):
        return self.outputs

    def get_providers(self):
        return ['CPUExecutionProvider']

    def run(self,output_names,feed):
        if not self.pointer:
            raise RuntimeError('Session is closed')
        expected={x.name for x in self.inputs}
        if set(feed)!=expected:
            raise ValueError('CPU chunk inputs differ: missing='+str(expected-set(feed))+' extra='+str(set(feed)-expected))
        requested=[x.name for x in self.outputs] if output_names is None else list(output_names)
        if not set(requested).issubset({x.name for x in self.outputs}):
            raise ValueError('Unknown graph output')
        a=self.api;input_values=[];array_keepalive=[];shapes=[]
        out_values=(P*len(requested))()
        try:
            for item in self.inputs:
                value=np.asarray(feed[item.name])
                if value.dtype!=item.dtype or not value.dtype.isnative:
                    raise TypeError('Wrong input dtype for '+item.name+': '+str(value.dtype))
                # Do not change scalar [] into [1]; shape graph scalars cross chunk boundaries.
                if not value.flags.c_contiguous:
                    value=np.ascontiguousarray(value)
                if len(item.shape)!=value.ndim or any(isinstance(d,int) and d>=0 and d!=value.shape[i]
                                                        for i,d in enumerate(item.shape)):
                    raise ValueError('Wrong input shape for '+item.name)
                array_keepalive.append(value)
                shape=(I64*value.ndim)(*value.shape);shapes.append(shape)
                pointer=P()
                a.call('CreateTensorWithDataAsOrtValue',[P,P,Z,c.POINTER(I64),Z,I,PP],
                       a.memory,P(value.ctypes.data),value.nbytes,shape,value.ndim,ENUMS[value.dtype],c.byref(pointer))
                input_values.append(pointer)
            in_names=(CP*len(self.inputs))(*(x.name.encode('utf-8') for x in self.inputs))
            out_names=(CP*len(requested))(*(x.encode('utf-8') for x in requested))
            in_values=(P*len(input_values))(*(x.value for x in input_values))
            a.call('Run',[P,P,c.POINTER(CP),PP,Z,c.POINTER(CP),Z,PP],self.pointer,None,
                   in_names,in_values,len(input_values),out_names,len(requested),out_values)
            result=[]
            for pointer in out_values:
                info=P();data=P()
                try:
                    a.call('GetTensorTypeAndShape',[P,PP],pointer,c.byref(info))
                    dtype,shape=a.tensor_description(info)
                    if not all(isinstance(d,int) and d>=0 for d in shape):
                        raise ValueError('Runtime returned an unresolved shape')
                    elements=math.prod(shape)
                    a.call('GetTensorMutableData',[P,PP],pointer,c.byref(data))
                    raw=c.string_at(data,elements*dtype.itemsize) if elements else b''
                    result.append(np.frombuffer(raw,dtype=dtype,count=elements).copy().reshape(shape))
                finally:
                    a.release('TensorTypeAndShapeInfo',info)
            return result
        finally:
            for pointer in input_values:
                a.release('Value',pointer)
            for pointer in out_values:
                a.release('Value',pointer)

    def close(self):
        if self.pointer:
            self.api.release('Session',self.pointer)
            self.pointer=P()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def backend_details():
    api=default_api()
    return {'backend':'ONNX Runtime native C API via ctypes','version':api.version,'api_version':17,
            'library':api.library_path,'library_sha256':sha256(api.library_path),
            'provider':'CPUExecutionProvider','python_ORT_wheel_required':False,
            'native_package':validate_native_files()}
