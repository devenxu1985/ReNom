# coding: utf-8

import json

import os

from bottle import HTTPResponse, request, route, run

import numpy as np

import pandas as pd

import pkg_resources

from sklearn import cluster, preprocessing

from renom.optimizer import Adam
from renom.tda.lens import PCA, TSNE, AutoEncoder
from renom.tda.topology import SearchableTopology

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


# トポロジのパラメータを管理するクラス
class Params(object):
    def __init__(self):
        self.avg = None
        self.std = None
        self.filename = ""
        self.algorithm = None
        self.resolution = None
        self.overlap = None

    def set_file(self, filename, algorithm):
        self.filename = filename
        self.algorithm = algorithm

    def set_params(self, resolution, overlap):
        self.resolution = resolution
        self.overlap = overlap

    def is_file_changed(self, filename, algorithm):
        if (self.filename == filename) & (self.algorithm == algorithm):
            return False
        return True

    def is_params_changed(self, resolution, overlap):
        if (self.resolution == resolution) & (self.overlap == overlap):
            return False
        return True


def set_json_body(body):
    r = HTTPResponse(status=200, body=body)
    r.set_header('Content-Type', 'application/json')
    return r


@route("/")
def index():
    return pkg_resources.resource_string(__name__, "static/page.html")


@route("/static/<file_name>")
def static(file_name):
    return pkg_resources.resource_string(__name__, "static/" + file_name)


@route("/fonts/<file_name>")
def fonts(file_name):
    return pkg_resources.resource_string(__name__, "static/fonts/" + file_name)


# fileのロード
# TODO
# ディレクトリ決め打ちを変更
@route("/api/load", method="POST")
def load():
    filename = request.params.filename
    filepath = os.path.join(DATA_DIR, filename)

    try:
        # nanを含むデータは使わない
        pdata = pd.read_csv(filepath).dropna()
        # 画面で選択できるカラム名を取得する
        labels = pdata.columns[np.logical_or(pdata.dtypes == "float", pdata.dtypes == "int")]

        body = json.dumps({"labels": labels.tolist()})
        r = set_json_body(body)
        return r

    except IOError:
        body = json.dumps({"error": True})
        r = set_json_body(body)
        return r


# ノードをクリックした時に呼び出す関数
@route("/api/click", method="POST")
def click():
    node_index = int(request.params.clicknode)
    categorical_data, data = topology.get_hypercube(node_index)

    # データを標準化前の値に戻す
    data = (data * params.std) + params.avg

    # 少数の桁を丸める
    data = np.around(data, 2)

    body = json.dumps({"categorical_data": categorical_data.tolist(), "data": data.tolist()})
    r = set_json_body(body)
    return r


# トポロジを作成する関数
@route("/api/create", method="POST")
def create():
    # パラメータ取得
    filename = request.params.filename
    algorithm = int(request.params.algorithm)
    resolution = int(request.params.resolution)
    overlap = float(request.params.overlap)
    colored_by = int(request.params.colored_by)

    # filename, algorithmが変わっていたらデータの再読み込み&次元削減
    if params.is_file_changed(filename, algorithm):
        algorithms = [PCA(components=[0, 1]),
                      TSNE(components=[0, 1]),
                      AutoEncoder(epoch=500, batch_size=100, opt=Adam())]
        filepath = os.path.join(DATA_DIR, filename)
        pdata = pd.read_csv(filepath).dropna()

        # カテゴリデータを抽出
        categorical_data = np.array(pdata.loc[:, pdata.dtypes == "object"])
        topology.regist_categorical_data(categorical_data)

        # 数値データを抽出
        numerical_data = np.array(pdata.loc[:, np.logical_or(
            pdata.dtypes == "float", pdata.dtypes == "int")])
        params.avg = np.average(numerical_data, axis=0)
        params.std = np.std(numerical_data, axis=0)
        numerical_data = (numerical_data - params.avg) / params.std

        # 表示が切れるので、0~1ではなく0.01~0.99に正規化
        scaler = preprocessing.MinMaxScaler(feature_range=(0.01, 0.99))
        topology.fit_transform(numerical_data, metric=None, lens=[
                               algorithms[algorithm]], scaler=scaler)

    # filename, algorithm, resolution, overlapが変わっていたらトポロジーの再計算
    if params.is_file_changed(filename, algorithm) | params.is_params_changed(resolution, overlap):
        topology.map(resolution=resolution, overlap=overlap,
                     clusterer=cluster.DBSCAN(eps=25, min_samples=1))

    # paramsの更新
    if params.is_file_changed(filename, algorithm):
        params.set_file(filename, algorithm)
    if params.is_params_changed(resolution, overlap):
        params.set_params(resolution, overlap)

    cdata = topology.data[:, colored_by]
    topology.color(cdata.reshape(-1, 1))

    # postデータのバイナリから元の文字列を復元
    # TODO
    search_value = request.params.search_value
    if len(search_value) > 0:
        bytes_str = b""
        for i in search_value.split(","):
            bytes_str += int(i).to_bytes(1, byteorder='big')
        value = bytes_str.decode('utf-8')
        topology.search(value)

    max_scale = 80 / resolution
    if max_scale > 2:
        max_scale = 2.0
    scaler = preprocessing.MinMaxScaler(feature_range=(0.3, max_scale))
    topology.node_sizes = scaler.fit_transform(topology.node_sizes)

    body = json.dumps({"nodes": topology.nodes.tolist(),
                       "edges": topology.edges.tolist(),
                       "colors": topology.colorlist,
                       "node_sizes": topology.node_sizes.tolist()})
    r = set_json_body(body)
    return r


global topology
topology = SearchableTopology(verbose=0)

global params
params = Params()

run(host="0.0.0.0", port=8080)
