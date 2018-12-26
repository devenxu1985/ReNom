import renom as rm
import numpy as np


def compare(nd_value, ad_value):
    print('ad=')
    print(ad_value)
    print('nd=')
    print(nd_value)
    assert np.allclose(nd_value, ad_value, atol=1e-5, rtol=1e-3)


def test_basic_add():

    v1 = np.random.rand(2, 2)
    v2 = np.random.rand(2, 2)
    v3 = v1 + v2
    v4 = np.random.rand(2, 2)
    v5 = v3 + v4

    g1 = rm.graph.StaticVariable(v1)
    g2 = rm.graph.StaticVariable(v2)
    g3 = g1 + g2
    g4 = rm.graph.StaticVariable(v4)
    g5 = g3 + g4

    compare(v5, g5.as_ndarray())

    new_v1 = np.random.rand(2, 2)
    g1.value = new_v1

    new_v5 = new_v1 + v2 + v4
    g5.forward()
    compare(new_v5, g5.as_ndarray())


def test_basic_lstm():

    np.random.seed(45)
    v = np.random.rand(2, 2)
    layer = rm.graph.LstmGraphElement(3)
    t = np.random.rand(2, 3)
    loss = rm.graph.MeanSquaredGraphElement()
    opt = rm.graph.sgd_update(0.01, 0.4)
    p_l = 9999
    for i in range(3):
        layer.reset()
        l = loss(layer(v), t)
        l_arr = l.as_ndarray()
        print(l_arr)
        assert l_arr < p_l
        p_l = l_arr
        l.backward().update(opt)


def test_slices(use_gpu):
    rm.set_cuda_active(use_gpu)

    a = np.random.rand(3, 3, 3)
    A = rm.graph.StaticVariable(a)
    b = a[:, 1, 0:2]
    B = A[:, 1, 0:2]
    compare(b, B.as_ndarray())


def test_optimizer(use_gpu):

    rm.set_cuda_active(use_gpu)
    np.random.seed(45)
    v = np.random.rand(2, 2)
    layer = rm.graph.DenseGraphElement(3)
    t = np.random.rand(2, 3)
    loss = rm.graph.MeanSquaredGraphElement()
    opt = rm.graph.adam_update()
    p_l = 9999
    for i in range(5):
        l = loss(layer(v), t)
        l_arr = l.as_ndarray()
        print(l_arr)
        assert l_arr < p_l
        p_l = l_arr
        l.backward().update(opt)


def test_inference_executor(use_gpu):
    rm.set_cuda_active(use_gpu)

    v = np.random.rand(20, 3)
    layer = rm.graph.DenseGraphElement(4)
    t = np.random.rand(20, 4)
    loss = rm.graph.MeanSquaredGraphElement()
    opt = rm.graph.sgd_update()
    data, target = rm.graph.DistributorElement(v, t, batch_size=2).getOutputGraphs()
    exe = loss(layer(data), target).getInferenceExecutor()
    exe.execute(epochs=1)


def test_training_executor(use_gpu):
    rm.set_cuda_active(use_gpu)

    v = np.random.rand(20, 3)
    layer = rm.graph.DenseGraphElement(4)
    t = np.random.rand(20, 4)
    loss = rm.graph.MeanSquaredGraphElement()
    opt = rm.graph.sgd_update()
    data, target = rm.graph.DistributorElement(v, t, batch_size=2).getOutputGraphs()
    exe = loss(layer(data), target).getTrainingExecutor()
    exe.execute(epochs=1)


def test_finalizer(use_gpu):
    rm.set_cuda_active(use_gpu)

    np.random.seed(45)
    v = np.random.rand(2, 1, 3, 4)
    layer1 = rm.graph.ConvolutionalGraphElement(channels=2)
    res = rm.graph.ReshapeGraphElement([-1])
    layer2 = rm.graph.DenseGraphElement(3)
    t = np.random.rand(2, 3)
    loss = rm.graph.MeanSquaredGraphElement()
    opt = rm.graph.sgd_update()

    z = v
    z = layer1(z)
    z = res(z)
    z = layer2(z)
    z = loss(z, t)
    z._fwd.finalize()


def test_sequential(use_gpu):
    rm.set_cuda_active(use_gpu)

    np.random.seed(45)
    v = np.random.rand(4, 4)
    model = rm.graph.SequentialSubGraph([
        rm.graph.DenseGraphElement(3),
        rm.graph.DenseGraphElement(1),
        rm.graph.DenseGraphElement(5),
    ])
    z = model(v).as_ndarray()
    assert z.shape == (4, 5)
