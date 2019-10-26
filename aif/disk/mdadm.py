class Member(object):
    def __init__(self, member_xml, partobj):
        self.xml = member_xml
        self.device = partobj
        self.devpath = self.device.devpath
        pass

class Array(object):
    def __init__(self, array_xml):
        self.devpath = None
        pass
