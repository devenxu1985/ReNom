
from __future__ import division
import numpy as np
from renom.cuda import cuda as cu
from renom.core import Node, Variable, Pow
import renom.operation as op
import renom.utility.initializer as init
from .parameterized import Parametrized
from renom.cuda.gpuvalue import *


def normalized_form(x):
    return op.sqrt(op.sum(op.square(x), keepdims=True))


class weightnorm(Node):
    def __new__(cls, x, weight, gain, bias):
        return cls.calc_value(x, weight, gain, bias)

    @classmethod
    def _oper_cpu(cls, x, weight, gain, bias):
        assert len(x.shape) is 2, \
            "Currently only normalizes for dense networks."
        w = weight / normalized_form(weight) * gain
        ret = cls._create_node(op.dot(x, w) + bias)
        ret.attrs._x = x
        ret.attrs._w = w
        ret.attrs._weight = weight
        ret.attrs._gain = gain
        ret.attrs._bias = bias
        return ret

    @classmethod
    def _oper_gpu(cls, x, weight, gain, bias):
        assert len(x.shape) is 2, \
            "Currently only normalizes for dense networks."
        w = get_gpu(weight) / normalized_form(get_gpu(weight)) * get_gpu(gain)
        ret = cls._create_node(get_gpu(op.dot(get_gpu(x), w) + get_gpu(bias)))
        ret.attrs._x = x
        ret.attrs._w = w
        ret.attrs._weight = weight
        ret.attrs._gain = gain
        ret.attrs._bias = bias
        return ret

    def _backward_cpu(self, context, dy, **kwargs):
        x = self.attrs._x
        w = self.attrs._w
        gain = self.attrs._gain
        weight = self.attrs._weight
        dx = op.dot(dy, w.T)
        normal_dw = op.dot(x.T, dy)

        dgain = normal_dw * w / gain
        dw = w / weight * (normal_dw - np.sum(w * normal_dw / gain, keepdims=True) * w / gain)
        db = np.ones_like(dy) * dy

        if isinstance(self.attrs._x, Node):
            self.attrs._x._update_diff(context, dx, **kwargs)
        self.attrs._gain._update_diff(context, np.sum(dgain, axis=0, keepdims=True), **kwargs)
        self.attrs._weight._update_diff(context, dw, **kwargs)
        self.attrs._bias._update_diff(context, np.sum(db, axis=0, keepdims=True), **kwargs)

    def _backward_gpu(self, context, dy, **kwargs):
        x = get_gpu(self.attrs._x)
        w = get_gpu(self.attrs._w)
        gain = get_gpu(self.attrs._gain)
        weight = get_gpu(self.attrs._weight)
        dx = get_gpu(op.dot(dy, w.T))
        normal_dw = get_gpu(op.dot(x.T, dy))
        w_normed = get_gpu(normalized_form(weight))
        dgain = normal_dw * weight / w_normed
        dw = (get_gpu(1 / w_normed * normal_dw) -
              get_gpu(get_gpu(op.sum(get_gpu(weight * normal_dw), keepdims=True)) *
              weight / (get_gpu(op.square(w_normed)) * w_normed))) * gain
        db = get_gpu(self.attrs._bias).ones_like_me()
        if isinstance(self.attrs._x, Node):
            self.attrs._x._update_diff(context, dx, **kwargs)
        self.attrs._gain._update_diff(context, op.sum(dgain, axis=0, keepdims=True), **kwargs)
        self.attrs._weight._update_diff(context, dw, **kwargs)
        self.attrs._bias._update_diff(context, op.sum(db, axis=0, keepdims=True), **kwargs)


class WeightNormalization(Parametrized):
    ''' Weight Normalization Model [1]
    A modification to the normal dense layer model, where the weight is normalized and multiplied
    by a trainable gain factor.

    The weight in this form is parameterized by the form:
        w = v / ||v|| * gain

    Note that in this version, gain is taken linear on the input s giving:
        gain = s.
    The original paper suggests a potential gain parameterization by taking the
    exponential value of s instead:
        gain = exp(s)

    There might be support for this later.

    Example:
        In [1]: import numpy as np
        In [2]: import renom as rm
        In [3]: x = np.random.rand(2,3)
        In [4]: layer = rm.WeightNormalization(4)
        In [5]: layer(x)
        Out[5]:
        weightnorm([[1.00133252, 1.00713646, 0.98452991, 1.0043143],
                    [0.983392 , 1.01545942, 0.99134618, 1.01834679]],
                    dtype=float32)

    .. [1] https://arxiv.org/abs/1602.07868
    '''

    def __init__(self, units, gain=0.1, initializer=init.GlorotNormal(), input_size=None):
        super(WeightNormalization, self).__init__(input_size)
        self._units = units
        self._gain = gain
        self._initializer = initializer

    def weight_initiallize(self, input_size):
        self.params = {
            "w": Variable(self._initializer((input_size[0], self._units)), auto_update=True),
            "gain": Variable(np.ones((1, self._units)) * self._gain, auto_update=True),
            "bias": Variable(np.ones((1, self._units)), auto_update=True)}

    def forward(self, x):
        return weightnorm(x, self.params["w"], self.params["gain"], self.params["bias"])
