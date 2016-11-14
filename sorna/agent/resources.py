import ctypes, ctypes.util
import operator
import os
import sys

_numa_supported = False

if sys.platform == 'linux':
    _libnuma_path = ctypes.util.find_library('numa')
    if _libnuma_path:
        _libnuma = ctypes.CDLL(_libnuma_path)
        _numa_supported = True


class libnuma:

    @staticmethod
    def node_of_cpu(core):
        if _numa_supported:
            return int(_libnuma.numa_node_of_cpu(core))
        else:
            return 0

    @staticmethod
    def num_nodes():
        if _numa_supported:
            return int(_libnuma.numa_num_configured_nodes())
        else:
            return 1

    @staticmethod
    def get_available_cores():
        try:
            return os.sched_getaffinity(os.getpid())
        except AttributeError:
            return {idx for idx in range(os.cpu_count())}

    @staticmethod
    def get_core_topology():
        topo = tuple([] for _ in range(libnuma.num_nodes()))
        for c in libnuma.get_available_cores():
            n = libnuma.node_of_cpu(c)
            topo[n].append(c)
        return topo


class CPUAllocMap:

    def __init__(self):
        self.core_topo = libnuma.get_core_topology()
        self.num_cores = len(libnuma.get_available_cores())
        self.num_nodes = libnuma.num_nodes()
        self.alloc_per_node = [0 for _ in range(self.num_nodes)]
        self.core_shares = [0 for _ in range(self.num_cores)]

    def alloc(self, num_cores):
        '''
        Find a most free set of CPU cores and return a tuple of the NUMA node
        index and the set of integers indicating the found cores.
        This method guarantees that all cores are alloacted within the same
        NUMA node.
        '''
        node, current_alloc = min(enumerate(self.alloc_per_node),
                                  key=operator.itemgetter(1))
        self.alloc_per_node[node] = current_alloc + num_cores

        shares = self.core_shares.copy()
        allocated_cores = set()
        for _ in range(num_cores):
            core, _ = min(enumerate(shares), key=operator.itemgetter(1))
            allocated_cores.add(core)
            shares[core] = sys.maxsize   # prune allocated one
            self.core_shares[core] += 1  # update the original share
        return node, allocated_cores

    def free(self, core_set):
        '''
        Remove the given set of CPU cores from the allocated shares.
        It assumes that all cores are in the same NUMA node.
        '''
        any_core = next(iter(core_set))
        node = libnuma.node_of_cpu(any_core)
        self.alloc_per_node[node] -= len(core_set)
        for c in core_set:
            self.core_shares[c] -= 1