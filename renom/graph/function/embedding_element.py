from renom.graph.core import UserGraph, operational_element, operation, GraphMultiStorage, GraphFactory, graph_variable
import renom.utility.initializer as init
import renom as rm
import numpy as np


class embedding_forward(operation):

    name = 'Embedding (F)'
    consumes = ['w']

    def __init__(self, output_size):
        assert isinstance(output_size, int), 'Embedding layer currently only accepts integers.'
        print(isinstance(output_size, int), output_size)
        self._output_size = output_size

    def setup(self, inputs):
        weights = inputs[1]['y']
        inputs = inputs[0]['y']
        assert isinstance(inputs, GraphMultiStorage), 'Received {}'.format(type(inputs))
        self.gpus = inputs.gpus
        self._init = init.GlorotNormal()
        self._inputs = inputs
        assert inputs.shape[1] == 1, 'Embedding layer expects an input size of 1.'
        weight_shape = (inputs.shape[1], self._output_size)
        weights.__init__(shape=weight_shape, gpus=self.gpus, initializer=self._init)
        output_shape = (inputs.shape[0], self._output_size)
        outputs = GraphMultiStorage(shape=output_shape, gpus=self.gpus)
        self._vars = {'x': inputs, 'w': weights, 'y': outputs}
        self._weights = weights
        self._outputs = outputs

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            rm.cuda.cuembedding_forward(self._inputs[gpu], self._weights[gpu], self._outputs[gpu])


class embedding_forward_cpu(embedding_forward):

    def perform(self):
        x = self._inputs['cpu']
        w = self._weights['cpu']
        index = x.astype(np.int)[:, 0]
        self._index = index
        ret = w[index]
        self._outputs['cpu'] = ret


class embedding_weight_backward(operation):

    name = 'Embedding Weight (B)'
    produces = ['w']

    def __init__(self, associated_forward):
        self._fwd_op = associated_forward

    def setup(self, inputs):
        inputs = inputs[0]['y']
        self._inputs = inputs

        gpus = inputs.gpus
        self.gpus = gpus
        fwd_ins = self._fwd_op.get_key('x')
        fwd_weights = self._fwd_op.get_key('w')
        output_shape = fwd_weights.shape

        outputs = GraphMultiStorage(shape=output_shape, gpus=gpus, initializer=None)

        self._vars = {'y': outputs, 'w': outputs, id(fwd_weights): outputs}

        self._fwd_ins = fwd_ins
        self._outputs = outputs

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            dy = self._outputs[gpu]
            rm.cuda.cusub(dy, dy, dy, handle)
            rm.cuda.cuembedding_backward(self._fwd_ins[gpu], self._inputs[gpu], self._outputs[gpu])


class embedding_weight_backward_cpu(embedding_weight_backward):

    def perform(self):
        index = self._fwd_op._index
        N = len(index)
        w = self._fwd_op._weights['cpu']
        dx = np.zeros(w.shape, dtype=w.dtype)
        dy = self._inputs['cpu']
        for i in range(N):
            dx[index[i]] += dy[i]
        self._outputs['cpu'] = dx


class EmbeddingGraph(UserGraph):

    def __init__(self, output_size, previous_element=None):

        fwd_op = embedding_forward(output_size) if rm.is_cuda_active(
        ) else embedding_forward_cpu(output_size)
        bwd_ops = [embedding_weight_backward(
            associated_forward=fwd_op) if rm.is_cuda_active() else embedding_weight_backward_cpu(fwd_op)]
        self.output_size = output_size

        super().__init__(forward_operation=fwd_op, backward_operations=bwd_ops, previous_elements=previous_element)


class Embedding(GraphFactory):
    """Embedding layer.
    This layer is the special case of dense layer. The case is that the input value is onehot encoded.
    Since the onehot encoded input is very sparse, the matrix product performed in the dense layer is redundant.

    The difference between dense layer and embedding layer is bellow.

    |
    | **[Dense layer]**
    |  data -> onehot encoding -> onehot data -> dense layer -> embedded data
    |
    | **[Embedding layer]**
    |  data -> embedding layer -> embedded data
    |
    |

    Args:
        output_size (int): Output unit size.
        input_size (int): Input unit size. This is same as number of embedding characters.
        initializer (Initializer): Initializer object for weight initialization.

    Example:
        >>> import numpy as np
        >>> import renom as rm
        >>> N = 4
        >>> a = np.arange(N).reshape(N, 1)
        >>> layer = rm.Embedding(output_size=1, input_size=8)
        >>> out = layer(a)

    Raises:
        Assertion error when output_size is not an integer or received shape is not of
        shape (N, 1).

    Note:
        1. This layer only accepts matrix which shape is (N, 1) and has integer value. *N is batch size.
        2. Both ``output_size`` and ``input_size`` must be specified.
    """

    def prepare(self, output_size, weight_decay=None):
        self.output_size = output_size
        self.params['w'] = graph_variable(weight_decay=weight_decay)
        self._bias = rm.graph.Bias()
        self.params['b'] = self._bias.params['b']

    def connect(self, other):
        ret = EmbeddingGraph(output_size=self.output_size,
                             previous_element=[other, self.params['w']])
        ret = self._bias(ret)
        return ret
