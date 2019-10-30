def xmlBool(xmlobj):
    # https://bugs.launchpad.net/lxml/+bug/1850221
    if isinstance(xmlobj, bool):
        return (xmlobj)
    if xmlobj.lower() in ('1', 'true'):
        return(True)
    elif xmlobj.lower() in ('0', 'false'):
        return(False)
    else:
        return(None)

class _Sizer(object):
    def __init__(self):
        def _getKeys(d, keylist = None):
            if not keylist:
                keylist = []
            for k, v in d.items():
                if isinstance(v, dict):
                    keylist.append(k)
                    keylist = _getKeys(v, keylist = keylist)
                else:
                    keylist.append(k)
            return (keylist)
        # We use different methods for converting between storage and BW, and different multipliers for each subtype.
        # https://stackoverflow.com/questions/5194057/better-way-to-convert-file-sizes-in-python
        # https://en.wikipedia.org/wiki/Orders_of_magnitude_(data)
        # https://en.wikipedia.org/wiki/Binary_prefix
        self.storageUnits = {'decimal': {'B': 0,
                                         'kB': 7,  # Kilobyte
                                         'MB': 17,  # Megabyte...
                                         'GB': 27,
                                         'TB': 37},
                             'binary': {'KiB': 10,  # Kibibyte
                                        'MiB': 20,  # Mebibyte...
                                        'GiB': 30,
                                        'TiB': 40}}
        # https://en.wikipedia.org/wiki/Bit#Multiple_bits
        self.bwUnits = {'b': None,
                        'bit': None,
                        'k': }
        self.valid_storage = list(self.storageUnits.keys())
        self.valid_storage.insert('nibble')
        self.valid_bw = _getKeys(self.bwUnits)

    def convert(self, n, suffix, target = None):
        pass

    def convertBW(self, n, suffix, target = None):
        inBits = n
        if suffix not in self.valid_bw:
            raise ValueError('suffix must be one of {0}'.format(', '.format(self.valid_bw)))
        if suffix != 'b':
            if self.bwUnits[suffix]:
                inBits = n * (10 ** self.bwUnits[suffix])
            else:
                inBits = None

    def convertStorage(self, n, suffix, target = None):
        inBytes = n
        if suffix not in self.valid_storage:
            raise ValueError('suffix must be one of {0}'.format(', '.format(self.valid_storage)))
        if suffix == 'nibble':
            inBytes = n * 0.5
        elif suffix != 'B':
            inBytes = float(n << self.storageUnits[suffix])
        if target:
            conversion = float(inBytes / float(1 << self.storageUnits[target]))
        else:
            conversion = {}
            for unit, shifter in self.storageUnits.items():
                conversion[unit] = float(inBytes / float(1 << self.storageUnits[unit]))
        return(conversion)


size = _Sizer()
