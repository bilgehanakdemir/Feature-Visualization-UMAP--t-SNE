from tqdm import tqdm

import gc

import numpy as np

import torch
from torch import nn
import torch.nn.functional as F
from torch import optim
import torch_optimizer as optim2


from imageclassification.kvs import GlobalKVS
import imageclassification.training.model as mdl

import matplotlib.pyplot as plt
import cv2

from imageclassification.training import QHAdam_function

def init_model():
    kvs = GlobalKVS()
    net = mdl.get_model(kvs['args'].experiment, kvs['args'].num_classes)

    if kvs['gpus'] > 1:
        net = nn.DataParallel(net)  #.to('cuda')

    net = net.to('cuda')
    return net


def init_optimizer(parameters):
    kvs = GlobalKVS()
    if kvs['args'].optimizer == 'adam':
        return optim.Adam(parameters, lr=kvs['args'].lr, weight_decay=kvs['args'].wd)
    #elif kvs['args'].optimizer == 'sgd':
     #   return optim.SGD(parameters, lr=kvs['args'].lr, weight_decay=kvs['args'].wd, momentum=0.9, nesterov=kvs['args'].set_nesterov)
#    elif kvs['args'].optimizer == 'QHM':
#          return optim2.QHM(parameters, lr=kvs['args'].lr, weight_decay=kvs['args'].wd, momentum=0.9)     #QHM optimizer added by.
    elif kvs['args'].optimizer == 'QHAdam':
        return optim2.QHAdam(parameters, lr=kvs['args'].lr, weight_decay=kvs['args'].wd)     #QHM optimizer added by.
        #return QHAdam_function.QHAdam(parameters, lr=kvs['args'].lr, weight_decay=kvs['args'].wd)
    else:
        raise NotImplementedError

def train_epoch(net, optimizer, train_loader):
    kvs = GlobalKVS()
    net.train(True)

    running_loss = 0.0
    n_batches = len(train_loader)
    
    epoch = kvs['cur_epoch']
    max_ep = kvs['args'].n_epochs
    print("epoch no: ",epoch+1)

    device = next(net.parameters()).device

    pbar = tqdm(total=n_batches)  # the number of expected iterations here is n_batches
    
    
    for i, batch in enumerate(train_loader):
        optimizer.zero_grad() #set the gradients to zero before starting backprob,PyTorch accumulates the gradients on subsequent backward passes
        #labels = batch['label'].long().to(device)
        labels = batch['label'].to(device)
        inputs = batch['img'].to(device)
        #print("inputs shape: ",inputs[0].shape)     #inputs shape[]:  torch.Size([3, 64, 64])
      
#        if i < 15:
#            fig = plt.figure(figsize=(10,10))
#            plt.imshow(cv2.resize(inputs[0][0].squeeze().to("cpu").numpy(), (64, 64)), cmap=plt.cm.gray)
#            fig.savefig(f'{i}.png', dpi=fig.dpi)

        outputs = net(inputs)
        loss = F.cross_entropy(outputs, labels)

        loss.backward()  # accumulates the gradient (by addition) for each parameter
        optimizer.step()  # performs a parameter update based on the current gradient
        running_loss += loss.item()  # adds to running_loss the scalar value held in the loss
        # loss represents the sum of losses over all examples in the batch

        gc.collect()
        pbar.set_description(
            f'[{epoch+1} | {max_ep}] Train loss: {running_loss / (i + 1):.3f} / Loss {loss.item():.3f}')
        pbar.update()

    gc.collect()
    pbar.close()

    # train_loss
    return running_loss / n_batches


def validate_epoch(net, test_loader):
    kvs = GlobalKVS()
    net.eval()

    running_loss = 0.0
    n_batches = len(test_loader)
    epoch = kvs['cur_epoch']
    max_ep = kvs['args'].n_epochs

    device = next(net.parameters()).device

    probs_lst = []
    gt_lst = []

    pbar = tqdm(total=n_batches)  #,disable = True

    correct = 0
    all_samples = 0
    with torch.no_grad():  # stop autograd from tracking history on Tensors; autograd records computation history on the fly to calculate gradients later
        for i, batch in enumerate(test_loader):
            #labels = batch['label'].long().to(device)
            labels = batch['label'].to(device)
            inputs = batch['img'].to(device)
            #print("inputs shape: ",inputs[0].shape)    #torch.Size([3, 64, 64])
                
#            if i == 70 :
#                print("batch: ",batch)
#                fig = plt.figure(figsize=(10,10))
#                plt.imshow(cv2.resize(inputs[0][0].squeeze().to("cpu").numpy(), (64, 64)), cmap=plt.cm.gray)
#                fig.savefig(f'{i}.png', dpi=fig.dpi)

            outputs = net(inputs)

            loss = F.cross_entropy(outputs, labels)

            probs_batch = F.softmax(outputs, 1).data.to('cpu').numpy()
            gt_batch = batch['label'].numpy()

            probs_lst.extend(probs_batch.tolist())
            gt_lst.extend(gt_batch.tolist())

            running_loss += loss.item()

            pred = np.array(probs_lst).argmax(1)
            correct += np.equal(pred, np.array(gt_lst)).sum()
            all_samples += len(np.array(gt_lst))

            gc.collect()
            pbar.set_description(
                f'[{epoch+1} | {max_ep}] Val_acc: {100. * correct / all_samples:.0f}%')
            pbar.update()

        gc.collect()
        pbar.close()

    # val_loss, preds, gt, val_acc
    return running_loss / n_batches, np.array(probs_lst), np.array(gt_lst), correct / all_samples