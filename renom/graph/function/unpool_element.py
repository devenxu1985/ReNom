import renom as rm
from renom.layers.function.utils import im2col, col2im, imnpool, poolnim
from renom.graph.core import operation, learnable_graph_element, multi_gpu_variable, GraphFactory
import numpy as np

class unpool_forward(operation):

  name = 'Pool (F)'

  def __init__(self, prev_pool):
    self._prev_pool = prev_pool

  def setup(self, inputs, storage):

    inputs = inputs[0]['y']

    self._inputs = inputs
    prev_pool = self._prev_pool

    out_shape = prev_pool._inputs.shape
    
    self.gpus = inputs.gpus
    self._prev_in = prev_pool._inputs
    outs = multi_gpu_variable(shape = out_shape, gpus = self.gpus)
    self._outputs = outs
    self._vars = {'y' : outs}
    if rm.is_cuda_active():
      pd = prev_pool._pool_desc
      self._pool_desc = pd

  def perform(self):
    for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
      x = self._inputs[gpu]
      px = self._prev_in[gpu]
      dx = self._outputs[gpu]
      rm.cuda.cuPoolingBackward(handle, self._pool_desc, px, x, x, dx)

class unpool_forward_cpu(unpool_forward):

  def perform(self):
    x = self._inputs['cpu']
    if self._dims == 2:
      col = im2col(x, self._outputs.shape[2:], self._kernel, self._stride, self._padding)
      n, ic, kh, kw, oh, ow = col.shape
      col = col.reshape(n, ic, kh * kw, oh, ow)
      index = np.argmax(col, axis=2)
      self._index = index
      ret = np.max(col, axis=2)
    else:
      ret = imnpool(x, self._kernel, self._stride, self._padding, mode = 'max')
    self._outputs['cpu'] = ret 
    

class unpool_backward(operation):

  name = 'Pool (B)'

  def __init__(self, associated_forward):
    self._fwd_op = associated_forward

  def setup(self, inputs, storage):
    
    inputs = inputs[0]['y']
    self._inputs = inputs
    out_shape = self._fwd_op._inputs.shape
    self._fwd_in = self._fwd_op._inputs
    self._fwd_out = self._fwd_op._outputs
    self.gpus = inputs.gpus
    outs = multi_gpu_variable(shape = out_shape, gpus = self.gpus)
    self._outputs = outs
    self._vars = { 'y' : outs , id(self._fwd_in) : outs}
    

  def perform(self):
    for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
      rm.cuda.cuPoolingBackward(handle, self._fwd_op._pool_desc, self._fwd_in[gpu], self._fwd_out[gpu], self._inputs[gpu], self._outputs[gpu]) 

class unpool_backward_cpu(unpool_backward):

  def perform(self):
    dims = self._fwd_op._dims
    dy = self._inputs['cpu']
    N = len(dy)
    x = self._fwd_op._inputs['cpu']
    index = self._fwd_op._index
    in_shape = self._fwd_op._inputs.shape
    out_shape = self._fwd_op._outputs.shape
    col = np.zeros((N, in_shape[1], self._fwd_op._kernel[0], self._fwd_op._kernel[1],
                       out_shape[2], out_shape[3]))
    col_k = np.rollaxis(col.reshape(N, in_shape[1], -1,
                          out_shape[2], out_shape[3]), 2)
    for i in np.ndindex(N, in_shape[1], out_shape[2], out_shape[3]):
      col_k[index[i]][i] = dy[i]
    dx = col2im(col, in_shape[2:], self._fwd_op._stride, self._fwd_op._padding)
    self._outputs['cpu'] = dx

 

class MaxUnPoolElement(learnable_graph_element):

  has_back = True

  def __init__(self, prev_pool, previous_element = None):
    fwd_op = unpool_forward(prev_pool) if rm.is_cuda_active() else unpool_forward_cpu(prev_pool)
    bwd_ops = [ unpool_backward(fwd_op) if rm.is_cuda_active() else unpool_backward_cpu(fwd_op)]
    super().__init__(forward_operation = fwd_op, backward_operations = bwd_ops, previous_elements = previous_element)


class MaxUnPoolGraphElement(GraphFactory):

  
  def __init__(self, prev_pool):
    self._prev = prev_pool._fwd._op

  def connect(self, other):
    ret = MaxPoolElement(self._prev, previous_element = [ other ])
    return ret