try:
    import gi
    gi.require_version('BlockDev', '2.0')
    from gi.repository import BlockDev, GLib
    has_mod = True
except ImportError:
    # This is ineffecient; the native gobject-introspection module is preferred.
    # In Arch, this can be installed via the "extra" repository packages "libblockdev" and "python-gobject".
    import subprocess
    has_mod = False
##
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.mdadm_fallback as mdadm


class PV(object):
    def __init__(self, partobj):
        self.devpath = None
        pass


class VG(object):
    def __init__(self, vg_xml, lv_objs):
        self.devpath = None
        pass


class LV(object):
    def __init__(self, lv_xml, pv_objs):
        pass
