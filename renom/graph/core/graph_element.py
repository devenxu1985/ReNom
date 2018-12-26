import numpy as np
import abc
import functools


class graph_element(abc.ABC):
    '''
      This class implements basic logic of the graph. The graph is constructed as a tree with
      references to both the previous and following elements.

      The basic tree maintains a depth variable with the rule that its depth is the maximum
      of its predecessors plus 1. If updated, all following depth values will be recalculated.

    '''

    def __init__(self, previous_elements=None):

        if isinstance(previous_elements, graph_element):
            previous_elements = [previous_elements]
        elif previous_elements is None:
            previous_elements = []

        self._visited = False
        depth = 0
        for prev in previous_elements:
            prev.add_next(self)
        # This should perform a copy, not a reference store.
        self._previous_elements = previous_elements
        self.depth = depth
        self._next_elements = []
        self.update_depth()

    def add_input(self, new_input):
        if new_input not in self._previous_elements:
            self._previous_elements.append(new_input)
        new_input.add_next(self)
        self.update_depth()

    def add_next(self, new_next):
        self._next_elements.append(new_next)

    def remove_input(self, prev_input):
        if prev_input in self._previous_elements:
            prev_input.remove_next(self)
            self._previous_elements.remove(prev_input)

    def remove_next(self, prev_next):
        if prev_next in self._next_elements:
            self._next_elements.remove(prev_next)

    def update_depth(self):
        for prev in self._previous_elements:
            if prev.depth >= self.depth:
                self.depth = prev.depth + 1
                for next_element in self._next_elements:
                    next_element.update_depth()

    def __lt__(self, other):
        return self.depth < other.depth

    @abc.abstractmethod
    def forward(self):
        pass

    @abc.abstractmethod
    def __repr__(self):
        pass

    def walk_tree(func):
        def cleanup(self):
            '''
            This method reset all the elements in the
            tree to a non-visited state.
            '''
            if self._visited is False:
                return
            self._visited = False
            for prev in self._previous_elements:
                cleanup(prev)
            for elem in self._next_elements:
                cleanup(elem)

        def walk_func(self, func, res, *args, **kwargs):
            if self._visited is True:
                return

            self._visited = True
            assert isinstance(res, dict) or isinstance(res, list)
            for prev in self._previous_elements:
                walk_func(prev, func, res, *args, **kwargs)

            ret = func(self, *args, **kwargs)
            if ret is not None:
                if isinstance(res, dict):
                    if self.depth not in res:
                        res[self.depth] = []
                    res[self.depth].append(ret)
                else:
                    res.append(ret)

            self._next_elements.sort()
            for elem in self._next_elements:
                if elem.depth == self.depth + 1:
                    walk_func(elem, func, res, *args, **kwargs)

        @functools.wraps(func)
        def ret_func(self, *args, flatten=False, **kwargs):
            if flatten is True:
                ret = []
            else:
                ret = {}
            walk_func(self, func, ret, *args, **kwargs)
            cleanup(self)
            return ret
        return ret_func

    def clear(self):
        for elem in self._previous_elements:
            elem.remove_next(self)
        self._previous_elements = []
        self.depth = 0
        self._start_points = []
        for elem in self._next_elements:
            elem.remove_input(self)
        self._next_elements = []
