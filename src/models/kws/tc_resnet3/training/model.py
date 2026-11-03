import torch
from torch import nn

class ResidualBlock(nn.Module):
    def __init__(self, cin, cout, stride=1, dropout=0.1):
        super().__init__()
        self.main = nn.Sequential(
            nn.Conv1d(cin,cout,3,stride=stride,padding=1,bias=False),
            nn.BatchNorm1d(cout),nn.ReLU(inplace=True),
            nn.Conv1d(cout,cout,3,padding=1,bias=False),
            nn.BatchNorm1d(cout))
        self.shortcut = (nn.Identity() if cin==cout and stride==1 else
            nn.Sequential(nn.Conv1d(cin,cout,1,stride=stride,bias=False),nn.BatchNorm1d(cout)))
        self.act=nn.ReLU(inplace=True)
        self.drop=nn.Dropout(dropout)
    def forward(self,x):
        return self.drop(self.act(self.main(x)+self.shortcut(x)))

class TCResNet(nn.Module):
    """Narrow temporal residual KWS network, TC-ResNet-inspired, not official layer-identical TC-ResNet8."""
    def __init__(self,num_classes=15,channels=(16,24,32),pool_bins=8,dropout=0.1):
        super().__init__()
        a,b,c=channels
        self.stem=nn.Sequential(nn.Conv1d(40,a,3,padding=1,bias=False),nn.BatchNorm1d(a),nn.ReLU())
        self.blocks=nn.Sequential(ResidualBlock(a,a,1,dropout),ResidualBlock(a,b,2,dropout),ResidualBlock(b,c,2,dropout))
        self.pool=nn.AdaptiveAvgPool1d(pool_bins)
        self.fc=nn.Linear(c*pool_bins,num_classes)
    def forward(self,x):
        if x.ndim==4:
            if x.shape[1]!=1:raise ValueError('expected [B,1,40,T]')
            x=x[:,0]
        if x.ndim!=3 or x.shape[1]!=40:raise ValueError('expected [B,40,T]')
        x=self.stem(x)
        x=self.blocks(x)
        return self.fc(self.pool(x).flatten(1))

if __name__=='__main__':
    m=TCResNet()
    x=torch.zeros(2,1,40,248)
    print('params:',sum(p.numel() for p in m.parameters()),'output:',m(x).shape)
