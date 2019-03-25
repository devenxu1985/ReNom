#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2019, Grid.
#
# This source code is licensed under the ReNom Subscription Agreement, version 1.0.
# ReNom Subscription Agreement Ver. 1.0 (https://www.renom.jp/info/license/index.html)

import numpy as np
import renom as rm
from renom.graph.core import UserGraph, operation, GraphFactory, \
    graph_variable, GraphMultiStorage


class selu_forward(operation):
    '''Selu forward operation class.
    '''

    name = 'Selu (F)'

    def __init__(self):
        alpha = 1.6732632423543772848170429916717
        lamda = 1.0507009873554804934193349852946
        self._alpha = alpha
        self._lamda = lamda

    def setup(self, inputs):
        '''Prepares workspaces for this operation.

        Args:
            inputs (list of GraphMultiStorage): Input data to this operation.

        selu_forward class requires inputs to contain following keys.

        +-------+-----+--------------------------------+
        | Index | Key |              Role              |
        +=======+=====+================================+
        |   0   |  y  | Output of previous operation.  |
        +-------+-----+--------------------------------+
        '''

        inputs = inputs[0]['y']
        gpus = inputs.gpus
        self.gpus = gpus
        in_shape = inputs.shape
        outs = GraphMultiStorage(shape=in_shape, gpus=gpus)
        self._inputs = inputs
        self._outputs = outs
        self._vars = {'y': outs}

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            rm.cuda.cueru_forward(self._alpha, self._inputs[gpu], self._outputs[gpu])
            rm.cuda.cumul(self._outputs[gpu], self._lamda, self._outputs[gpu], handle)


class selu_forward_cpu(selu_forward):

    def perform(self):
        x = self._inputs['cpu']
        alpha = self._alpha
        lamda = self._lamda
        ret = np.where(x > 0, x, (np.exp(x) - 1) * alpha) * lamda
        self._outputs['cpu'] = ret


class selu_backward(operation):
    '''Selu backward operation class.

    Args:
        associated_forward (forward_operation): Corresponding forward operation.
    '''

    name = 'Selu (B)'

    def __init__(self, associated_forward):
        self._fwd_op = associated_forward
        self._alpha = self._fwd_op._alpha
        self._lamda = self._fwd_op._lamda

    def setup(self, inputs):
        '''Prepares workspaces for this operation.

        Args:
            inputs (list of GraphMultiStorage): Input data to this operation.

        selu_backward class requires inputs to contain following keys.

        +-------+-----+--------------------------------+
        | Index | Key |              Role              |
        +=======+=====+================================+
        |   0   |  y  | Output of previous operation.  |
        +-------+-----+--------------------------------+
        '''

        inputs = inputs[0]['y']
        gpus = inputs.gpus
        self.gpus = gpus
        in_shape = inputs.shape
        outs = GraphMultiStorage(shape=in_shape, gpus=gpus)
        self._inputs = inputs
        self._outputs = outs
        self._fwd_in = self._fwd_op._inputs
        self._vars = {'y': outs, id(self._fwd_op._inputs): outs}

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            rm.cuda.cueru_backward(self._alpha, self._fwd_in[gpu], self._outputs[gpu])
            rm.cu.cumul(self._outputs[gpu], self._inputs[gpu], self._outputs[gpu], handle)
            rm.cuda.cumul(self._outputs[gpu], self._lamda, self._outputs[gpu], handle)


class selu_backward_cpu(selu_backward):

    def perform(self):
        y = self._fwd_op._outputs['cpu']
        alpha = self._alpha
        lamda = self._lamda
        dy = self._inputs['cpu']
        ret = np.where(y > 0, dy, dy * (alpha + y)) * lamda
        self._outputs['cpu'] = ret


class SeluElement(UserGraph):

    def __init__(self, previous_elements=None):
        fwd_op = selu_forward() if rm.is_cuda_active() else selu_forward_cpu()
        bwd_ops = [selu_backward(fwd_op) if rm.is_cuda_active() else selu_backward_cpu(fwd_op)]
        super().__init__(forward_operation=fwd_op, backward_operations=bwd_ops, previous_elements=previous_elements)


class Selu(GraphFactory):
    '''A factory class of selu activation function element.

    .. math::

        \\alpha = 1.6732632423543772848170429916717 \\\\
        \lambda = 1.0507009873554804934193349852946 \\\\
        y = \lambda * max(x, \\alpha * (exp(x) - 1))

    Example:
        >>> import numpy as np
        >>> import renom.graph as rmg
        >>>
        >>> x = np.array([-1, 0, 1])
        >>>
        >>> layer = rmg.Elu()
        >>> layer(x)
        Elu (F):
        [-0.00632121  0.          1.        ]
        >>>
        >>> # Create element using function interface.
        >>> rmg.elu(x)
        Elu (F):
        [-0.00632121  0.          1.        ]

    '''

    def connect(self, other):
        ret = SeluElement(previous_elements=other)
        return ret


def selu(x):
    '''A function style factory of selu activation function element.

    For more information, please refer \
        :py:class:`~renom.graph.activation.selu_element.Selu`.
    '''

    return SeluElement(previous_elements=[x])
