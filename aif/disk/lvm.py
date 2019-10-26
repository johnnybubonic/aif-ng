class PV(object):
    def __init__(self, partobj):
        self.devpath = None
        pass

class LV(object):
    def __init__(self, lv_xml, pv_objs):
        pass

class Group(object):
    def __init__(self, vg_xml, lv_objs):
        self.devpath = None
        pass
