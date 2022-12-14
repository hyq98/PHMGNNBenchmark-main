import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv,  BatchNorm # noqa
from torch_geometric.nn import TopKPooling,  EdgePooling, ASAPooling, SAGPooling, global_mean_pool

class GCN(torch.nn.Module):
    def __init__(self, feature, out_channel,pooltype):
        super(GCN, self).__init__()

        self.pool1, self.pool2 = self.poollayer(pooltype)

        self.GConv1 = GCNConv(feature,1024)
        self.bn1 = BatchNorm(1024)

        self.GConv2 = GCNConv(1024,1024)
        self.bn2 = BatchNorm(1024)

        self.fc = nn.Sequential(nn.Linear(1024, 512), nn.ReLU(inplace=True))
        self.dropout = nn.Dropout(0.2)
        self.fc1 = nn.Sequential(nn.Linear(512, out_channel))


    def forward(self, data, pooltype):
        x, edge_index, batch= data.x, data.edge_index, data.batch
        # x {250,512}
        x = self.GConv1(x, edge_index) # x {250,1024}
        print(x.shape)
        print(edge_index.shape)
        x = self.bn1(x) # x {250,1024}
        print(x.shape)
        x = F.relu(x) # x {250,1024}
        print(x.shape)
        x, edge_index, batch = self.poolresult(self.pool1,pooltype,x, edge_index, batch) # x {125,1024}
        print(x.shape)
        print(edge_index.shape)
        x1 = global_mean_pool(x, batch) # x {125,1024} # x1 {25,1024}
        print(x1.shape)
        x = self.GConv2(x, edge_index)  # x {125,1024}
        print(x.shape)
        x = self.bn2(x)
        print(x.shape)
        x = F.relu(x)
        print(x.shape)
        x, edge_index, batch = self.poolresult(self.pool2, pooltype, x, edge_index, batch) # x {84,1024} edge_index{2,290}
        print(x.shape)
        print(edge_index.shape)
        x2 = global_mean_pool(x, batch)# x2 {25,1024}
        print(x2.shape)
        x = x1 + x2 # x {25,1024}
        print(x.shape)

        x = self.fc(x) # x {64,512}
        x = self.dropout(x) # x {64,1024}
        x = self.fc1(x) # x {64,1024}

        return x

    def poollayer(self, pooltype):

        self.pooltype = pooltype

        if self.pooltype == 'TopKPool':
            self.pool1 = TopKPooling(1024)
            self.pool2 = TopKPooling(1024)
        elif self.pooltype == 'EdgePool':
            self.pool1 = EdgePooling(1024)
            self.pool2 = EdgePooling(1024)
        elif self.pooltype == 'ASAPool':
            self.pool1 = ASAPooling(1024)
            self.pool2 = ASAPooling(1024)
        elif self.pooltype == 'SAGPool':
            self.pool1 = SAGPooling(1024)
            self.pool2 = SAGPooling(1024)
        else:
            print('Such graph pool method is not implemented!!')

        return self.pool1, self.pool2

    def poolresult(self,pool,pooltype,x,edge_index,batch):

        self.pool = pool

        if pooltype == 'TopKPool':
            x, edge_index, _, batch, _, _ = self.pool(x=x, edge_index=edge_index, batch=batch)
        elif pooltype == 'EdgePool':
            x, edge_index, batch, _ = self.pool(x=x, edge_index=edge_index, batch=batch)
        elif pooltype == 'ASAPool':
            x, edge_index, _, batch, _ = self.pool(x=x, edge_index=edge_index, batch=batch)
        elif pooltype == 'SAGPool':
            x, edge_index, _, batch, _, _ = self.pool(x=x, edge_index=edge_index, batch=batch)
        else:
            print('Such graph pool method is not implemented!!')

        return x, edge_index, batch