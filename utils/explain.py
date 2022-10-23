import torch
import torch.nn.functional as F

import numpy as np

import train_graph_diagnosis
from models import GCN
import matplotlib.pyplot as plt
import hyperparameters as hp
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D
import matplotlib
import matplotlib.cm as cm
from skimage.io import imread
from cairosvg import svg2png, svg2ps
import os
from torch_geometric.data import DataLoader
import pandas as pd
from rdkit import Chem
from sklearn.preprocessing import MinMaxScaler
from tqdm import tqdm
import random
import time
import datasets
import logging
import warnings
import models
from torch import nn
# df = pd.read_csv('bbbp/BBBP.csv')

def img_for_mol(mol, atom_weights=[]):
    # print(atom_weights)
    highlight_kwargs = {}
    if len(atom_weights) > 0:
        norm = matplotlib.colors.Normalize(vmin=-1, vmax=1)
        cmap = cm.get_cmap('bwr')
        plt_colors = cm.ScalarMappable(norm=norm, cmap=cmap)

        atom_colors = {
            i: plt_colors.to_rgba(atom_weights[i]) for i in range(len(atom_weights))
        }
        highlight_kwargs = {
            'highlightAtoms': list(range(len(atom_weights))),
            'highlightBonds': [],
            'highlightAtomColors': atom_colors
        }
        # print(highlight_kwargs)


    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(280, 280)
    drawer.SetFontSize(1)

    mol = rdMolDraw2D.PrepareMolForDrawing(mol)
    drawer.DrawMolecule(mol, **highlight_kwargs)
                        # highlightAtoms=list(range(len(atom_weights))),
                        # highlightBonds=[],
                        # highlightAtomColors=atom_colors)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    svg = svg.replace('svg:', '')
    svg2png(bytestring=svg, write_to='tmp.png', dpi=100)
    img = imread('tmp.png')
    os.remove('tmp.png')
    return img

# def plot_explanations(model, data):
#     mol_num = int(data.mol_num.item())
#     # print(mol_num)
#     # row = df.iloc[mol_num]
#     # smiles = row.smiles
#     # mol = Chem.MolFromSmiles(smiles)
#     # breakpoint()
#
#     fig, axes = plt.subplots(2, 3, figsize=(12, 8))
#     # axes[0][0].imshow(img_for_mol(mol))
#     # axes[0][0].set_title(row['name'])
#     #
#     # axes[0][1].set_title('Adjacency Matrix')
#     # axes[0][1].imshow(data.A.cpu().numpy())
#     #
#     # axes[0][2].set_title('Feature Matrix')
#     # axes[0][2].imshow(data.x.cpu().detach().numpy())
#
#     axes[1][0].set_title('Saliency Map')
#     input_grads = model.input.grad.view(40, 8)
#     saliency_map_weights = saliency_map(input_grads)[:mol.GetNumAtoms()]
#     scaled_saliency_map_weights = MinMaxScaler(feature_range=(0,1)).fit_transform(np.array(saliency_map_weights).reshape(-1, 1)).reshape(-1, )
#     axes[1][0].imshow(img_for_mol(mol, atom_weights=scaled_saliency_map_weights))
#
#     axes[1][1].set_title('Grad-CAM')
#     final_conv_acts = model.final_conv_acts.view(40, 512)
#     final_conv_grads = model.final_conv_grads.view(40, 512)
#     grad_cam_weights = grad_cam(final_conv_acts, final_conv_grads)[:mol.GetNumAtoms()]
#     scaled_grad_cam_weights = MinMaxScaler(feature_range=(0,1)).fit_transform(np.array(grad_cam_weights).reshape(-1, 1)).reshape(-1, )
#     axes[1][1].imshow(img_for_mol(mol, atom_weights=scaled_grad_cam_weights))
#
#     axes[1][2].set_title('UGrad-CAM')
#     ugrad_cam_weights = ugrad_cam(mol, final_conv_acts, final_conv_grads)
#     axes[1][2].imshow(img_for_mol(mol, atom_weights=ugrad_cam_weights))
#
#     plt.savefig(f'explanations/{mol_num}.png')
#     plt.close('all')

def saliency_map(input_grads):
    # print('saliency_map')
    node_saliency_map = []
    for n in range(input_grads.shape[0]): # nth node
        node_grads = input_grads[n,:]
        node_saliency = torch.norm(F.relu(node_grads)).item()
        node_saliency_map.append(node_saliency)
    return node_saliency_map

def grad_cam(final_conv_acts, final_conv_grads):
    # print('grad_cam')
    node_heat_map = []
    alphas = torch.mean(final_conv_grads, axis=0) # mean gradient for each feature (512x1)
    for n in range(final_conv_acts.shape[0]): # nth node
        node_heat = F.relu(alphas @ final_conv_acts[n]).item()
        node_heat_map.append(node_heat)
    return node_heat_map

def ugrad_cam(mol, final_conv_acts, final_conv_grads):
    # print('new_grad_cam')
    node_heat_map = []
    alphas = torch.mean(final_conv_grads, axis=0) # mean gradient for each feature (512x1)
    for n in range(final_conv_acts.shape[0]): # nth node
        node_heat = (alphas @ final_conv_acts[n]).item()
        node_heat_map.append(node_heat)

    node_heat_map = np.array(node_heat_map[:mol.GetNumAtoms()]).reshape(-1, 1)
    pos_node_heat_map = MinMaxScaler(feature_range=(0,1)).fit_transform(node_heat_map*(node_heat_map >= 0)).reshape(-1,)
    neg_node_heat_map = MinMaxScaler(feature_range=(-1,0)).fit_transform(node_heat_map*(node_heat_map < 0)).reshape(-1,)
    return pos_node_heat_map + neg_node_heat_map


args = train_graph_diagnosis.parse_args()
if torch.cuda.is_available():
    device = torch.device("cuda")
    device_count = torch.cuda.device_count()
    logging.info('using {} gpus'.format(device_count))
    assert args.batch_size % device_count == 0, "batch size should be divided by device count"
else:
    warnings.warn("gpu is not available")
    device = torch.device("cpu")
    device_count = 1

# dataset = load_bbbp(hp.N)
phase = 'val'
epoch_start = time.time()
epoch_acc = 0
epoch_loss = 0.0


Dataset = getattr(datasets, args.data_name)
_, dataset = Dataset(args.sample_length, args.data_dir, args.Input_type,args.task).data_preprare()
random.Random(hp.shuffle_seed).shuffle(dataset)
split_idx = int(np.floor(len(dataset)*hp.train_frac))
# test_dataset = dataset[split_idx:]

loader =  DataLoader(dataset, batch_size=1,
                                  shuffle = True,
                                  num_workers=args.num_workers,
                                  pin_memory=(True if device == 'cuda' else False))

InputType = args.Input_type
if InputType == "TD":
    feature = args.sample_length
elif InputType == "FD":
    feature = int(args.sample_length / 2)
elif InputType == "other":
    feature = 1
else:
    print("The InputType is wrong!!")
# loader = DataLoader(test_dataset, batch_size=1, shuffle=False)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

model = getattr(models, args.model_name)(feature=feature,out_channel=Dataset.num_classes)
# model = GCN().to(device)
# model.load_state_dict(torch.load('E:\\code\\grape\\PHMGNNBenchmark-main\\checkpoint\\Node_GCN_CWRUKnn_FD_1017-170350\\46-0.9840-best_model.pth'))
# model.eval()
#
# optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
#
# print(model)
# model.train()
total_loss = 0
for data in tqdm(loader):
    # breakpoint()
    inputs = data
    labels = inputs.y
    model.load_state_dict(torch.load(
        'E:\\code\\grape\\PHMGNNBenchmark-main\\checkpoint\\Node_GCN_CWRUKnn_FD_1017-202536\\44-0.6080-best_model.pth'))
    model.eval()

    logits = model(inputs)
    pred = logits.argmax(dim=1)
    print(pred)
    print(logits.shape)
    print(data.y.shape)
    loss = nn.CrossEntropyLoss()(logits, data.y)
    loss.backward()
    # try:
        # plot_explanations(model, data)
    final_conv_acts = model.final_conv_acts.view(10, 512)
    final_conv_grads = model.final_conv_grads.view(10, 512)
    grad_cam_weights = grad_cam(final_conv_acts, final_conv_grads)
    scaled_grad_cam_weights = MinMaxScaler(feature_range=(0,1)).fit_transform(np.array(grad_cam_weights).reshape(-1, 1)).reshape(-1, )
    # plt.imshow(img_for_mol(, atom_weights=scaled_grad_cam_weights))

    # except ValueError as e:
    # except Exception as e:
    #     print(e)
    #     continue
    # # breakpoint()
    # img_for_mol(mol, atom_weights=scaled_grad_cam_weights)
    total_loss += loss.item() * data.num_graphs

