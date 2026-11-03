function Resolve-VivadoExecutable {
    if ($env:VIVADO_BIN -and (Test-Path -LiteralPath $env:VIVADO_BIN)) {
        return $env:VIVADO_BIN
    }
    foreach ($name in @("vivado.bat", "vivado")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    foreach ($candidate in @(
        'D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat',
        'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat',
        'C:\Xilinx\Vivado\2025.2\bin\vivado.bat'
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw "Vivado 2025.2 not found. Set VIVADO_BIN or add Vivado to PATH."
}
