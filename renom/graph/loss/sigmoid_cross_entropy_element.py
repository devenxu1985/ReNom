#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2019, Grid.
#
# This source code is licensed under the ReNom Subscription Agreement, version 1.0.
# ReNom Subscription Agreement Ver. 1.0 (https://www.renom.jp/info/license/index.html)

import numpy as np

import renom as rm
from renom.graph.core import operation, UserLossGraph, graph_element, GraphMultiStorage, GraphFactory
from renom.graph import populate_graph


class sigmoid_forward(operation):
    '''sigmoid cross entropy forward operation class.
    '''

    name = 'Sigmoid Cross Entropy(F)'
    roles = ['loss']

    def __init__(self, reduction='mean'):
        self.reduction = reduction

    def setup(self, inputs):
        '''Prepares workspaces for this operation.

        Args:
            inputs (list of GraphMultiStorage): Input data to this operation.

        sigmoid_forward class requires inputs to contain following keys.

        +-------+-----+------------------------------------+
        | Index | Key |              Role                  |
        +=======+=====+====================================+
        |   0   |  y  | Output of forward propagation.     |
        +-------+-----+------------------------------------+
        |   1   |  y  | Target of associated input.        |
        +-------+-----+------------------------------------+
        '''

        assert isinstance(inputs[1], dict)

        labels = inputs[1]['y']
        inputs = inputs[0]['y']
        assert labels.shape == inputs.shape
        out_shape = inputs.shape if self.reduction is None else (1, )
        gpus = inputs.gpus
        outs = GraphMultiStorage(shape=out_shape, gpus=gpus)
        self.gpus = gpus
        self._outputs = outs
        self._vars = {'y': outs}
        self._lbls = labels
        self._N = inputs.shape[0]
        self._inputs = inputs

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            x = self._inputs[gpu]
            N = x.shape[0]
            y = self._lbls[gpu]
            tmp1 = x.empty_like_me()
            tmp2 = x.empty_like_me()
            tmp3 = x.empty_like_me()
            rm.cuda.cusigmoid(x, tmp1)
            rm.cuda.cucross_entropy(tmp1, y, tmp2, handle)
            rm.cuda.cucross_entropy(-tmp1 + 1, -y + 1, tmp3, handle)
            rm.cuda.cuadd(tmp2, tmp3, tmp1, handle)
            rm.cuda.cunegate(tmp1, tmp1)

            if self.reduction is None:
                self._outputs[gpu].copy_from(tmp1)
            else:
                tmp = rm.cuda.cusum(tmp1, handle)
                if self.reduction == 'mean':
                    rm.cuda.cudiv(tmp, N, tmp, handle)
                elif self.reduction == 'sum':
                    pass
                else:
                    pass
                self._outputs[gpu].copy_from(tmp)


class sigmoid_forward_cpu(sigmoid_forward):

    def perform(self):
        x = self._inputs['cpu']
        y = self._lbls['cpu']
        N = len(x)
        z = 1 / (1 + np.exp(-x))
        self._z = z
        ret = -(y * np.log(z + 1e-8) + (1 - y) * np.log(1 - z + 1e-8))

        if self.reduction is None:
            pass
        else:
            ret = np.sum(ret).reshape(1,)
            if self.reduction == 'mean':
                ret /= N
            if self.reduction == 'sum':
                pass
        self._outputs['cpu'] = ret


class sigmoid_backward(operation):
    '''sigmoid cross entropy backward operation class.
    '''

    name = 'Sigmoid Cross Entropy(B)'

    def __init__(self, associated_forward):
        self._fwd_op = associated_forward

    def setup(self, inputs):
        '''Prepares workspaces for this operation.

        Args:
            inputs (list of GraphMultiStorage): Input data to this operation.

        sigmoid_backward class requires inputs to contain following keys.

        +-------+-----+------------------------------------+
        | Index | Key |              Role                  |
        +=======+=====+====================================+
        |   0   |  y  | Output of forward propagation.     |
        +-------+-----+------------------------------------+
        |   1   |  y  | Target associated to the input.    |
        +-------+-----+------------------------------------+
        |   2   |  y  | Output of forward operation.       |
        +-------+-----+------------------------------------+
        |   3   |  y  | Output of previous operation.      |
        +-------+-----+------------------------------------+
        '''

        self.reduction = self._fwd_op.reduction
        if len(inputs) > 3:
            self._dy = inputs[3]['y']
        else:
            self._dy = None
        predictions = inputs[0]['y']
        labels = inputs[1]['y']
        self._N = predictions.shape[0]
        self._graph_input = predictions
        self._label_input = labels

        gpus = predictions.gpus
        self.gpus = gpus
        output = GraphMultiStorage(shape=predictions.shape, gpus=gpus)
        act_out1 = GraphMultiStorage(shape=predictions.shape, gpus=gpus)

        self._act_out1 = act_out1
        self._outputs = output
        self._vars = {'y': output, 'dy': output, id(self._fwd_op._inputs): output}

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            if self._dy is not None:
                dy = self._dy[gpu]
            else:
                dy = 1
            rm.cuda.cusigmoid(self._graph_input[gpu], self._act_out1[gpu])
            rm.cuda.cusub(self._act_out1[gpu], self._label_input[gpu], self._outputs[gpu], handle)

            if self.reduction is None:
                pass
            else:
                if self.reduction == 'mean':
                    rm.cuda.cudiv(self._outputs[gpu], self._N, self._outputs[gpu], handle)
                elif self.reduction == 'sum':
                    pass
            rm.cuda.cumul(self._outputs[gpu], dy, self._outputs[gpu], handle)


class sigmoid_backward_cpu(sigmoid_backward):

    def perform(self):
        z = self._fwd_op._z
        y = self._label_input['cpu']
        N = len(z)
        if self._dy is not None:
            dy = self._dy['cpu']
        else:
            dy = 1

        ret = z - y

        if self.reduction is None:
            pass
        else:
            if self.reduction == 'mean':
                ret /= N
            elif self.reduction == 'sum':
                pass
        self._outputs['cpu'] = ret * dy


class SigmoidCrossEntropyElement(UserLossGraph):

    def __init__(self, reduction, previous_elements=None):
        fwd_op = sigmoid_forward(reduction) if rm.is_cuda_active(
        ) else sigmoid_forward_cpu(reduction)
        bwd_ops = [sigmoid_backward(fwd_op) if rm.is_cuda_active()
                   else sigmoid_backward_cpu(fwd_op)]
        super().__init__(forward_operation=fwd_op, backward_operations=bwd_ops, previous_elements=previous_elements)


@populate_graph
class SigmoidCrossEntropy(GraphFactory):
    '''A factory class of sigmoid cross entropy loss function element.

    Args:
        reduction (str): Reduction method. This accepts following keywords.

    +-----------+-------------------------------------------------------+
    | reduction |  description                                          |
    +===========+=======================================================+
    |  'mean'   | Calculates mean along axis=0 then sum up all element. |
    +-----------+-------------------------------------------------------+
    |  'sum'    | Calculates sum of all element.                        |
    +-----------+-------------------------------------------------------+
    |   None    | Reduction is not performed.                           |
    +-----------+-------------------------------------------------------+

    Example:
        >>> import numpy as np
        >>> import renom.graph as rmg
        >>> 
        >>> v1 = rmg.StaticVariable(np.random.rand(2, 2))
        >>> v2 = rmg.StaticVariable(np.random.rand(2, 2))
        >>> 
        >>> rmg.sigmoid_cross_entropy(v1, v2)
        Smooth L1 (F):
        [0.30044635]
    '''

    def prepare(self, reduction='mean'):
        self.reduction = reduction

    def connect(self, predictions, true_values):
        ret = SigmoidCrossEntropyElement(self.reduction, previous_elements=[
                                         predictions, true_values])
        return ret


@populate_graph
def sigmoid_cross_entropy(x, y, reduction='mean'):
    '''A function style factory of sigmoid cross entropy operation element.

    Args:
        x (UserGraph, ndarray): Left hand input.
        y (UserGraph, ndarray): Right hand input.
        reduction (str, None): Reduction method.


    For more information, please refer :py:class:`~renom.graph.loss.sigmoid_cross_entropy_element.SigmoidCrossEntropy`.
    '''

    return SigmoidCrossEntropy(reduction=reduction)(x, y)
