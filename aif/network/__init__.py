from . import _common
from . import netctl
from . import networkd
from . import networkmanager
from . import net

# No longer necessary:
# try:
#     from . import _common
# except ImportError:
#     pass  # GI isn't supported, so we don't even use a fallback.

# http://0pointer.net/blog/the-new-sd-bus-api-of-systemd.html
# https://www.youtube.com/watch?v=ZUX9Fx8Rwzg
# https://www.youtube.com/watch?v=lBQgMGPxqNo
# https://github.com/facebookincubator/pystemd has some unit/service examples
# try:
#     from . import networkd
# except ImportError:
#     from . import networkd_fallback as networkd
