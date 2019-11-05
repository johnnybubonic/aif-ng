import uuid
##
import parted  # https://www.gnu.org/software/parted/api/index.html

# META
ARCH_RELENG_KEY = '4AA4767BBC9C4B1D18AE28B77F2D434B9741E8AC'
VERSION = '0.2.0'
# blkinfo, mdstat, and pyparted are only needed for the non-gi fallbacks.
EXTERNAL_DEPS = ['blkinfo',
                 'gpg',
                 'lxml',
                 'mdstat',
                 'passlib',
                 'psutil',
                 'pyparted',
                 'pyroute2',
                 'pytz',
                 'requests',
                 'validators']
# PARTED FLAG INDEXING
PARTED_FSTYPES = sorted(list(dict(vars(parted.filesystem))['fileSystemType'].keys()))
PARTED_FLAGS = sorted(list(parted.partition.partitionFlag.values()))
PARTED_IDX_FLAG = dict(parted.partition.partitionFlag)
PARTED_FLAG_IDX = {v: k for k, v in PARTED_IDX_FLAG.items()}
# LIBBLOCKDEV BOOTSTRAPPING (ALLOWED VALUES IN CONFIG)
# https://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_entries_(LBA_2%E2%80%9333)
BD_PARTED_MAP = {'apple_tv_recovery': 'atvrecv',
                 'cpalo': 'palo',
                 'gpt_hidden': None,  # No parted equivalent
                 'gpt_no_automount': None,  # No parted equivalent
                 'gpt_read_only': None,  # No parted equivalent
                 'gpt_system_part': None,  # No parted equivalent
                 'hpservice': 'hp-service',
                 'msft_data': 'msftdata',
                 'msft_reserved': 'msftres'}
# GPT FSTYPES GUIDS
# I'm doing this now because if I didn't, I would probably need to do it later eventually.
# https://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_type_GUIDs
GPT_FSTYPE_GUIDS = ((1, 'EFI System', uuid.UUID(hex = 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B')),
                    (2, 'MBR partition scheme', uuid.UUID(hex = '024DEE41-33E7-11D3-9D69-0008C781F39F')),
                    (3, 'Intel Fast Flash', uuid.UUID(hex = 'D3BFE2DE-3DAF-11DF-BA40-E3A556D89593')),
                    (4, 'BIOS boot', uuid.UUID(hex = '21686148-6449-6E6F-744E-656564454649')),
                    (5, 'Sony boot partition', uuid.UUID(hex = 'F4019732-066E-4E12-8273-346C5641494F')),
                    (6, 'Lenovo boot partition', uuid.UUID(hex = 'BFBFAFE7-A34F-448A-9A5B-6213EB736C22')),
                    (7, 'PowerPC PReP boot', uuid.UUID(hex = '9E1A2D38-C612-4316-AA26-8B49521E5A8B')),
                    (8, 'ONIE boot', uuid.UUID(hex = '7412F7D5-A156-4B13-81DC-867174929325')),
                    (9, 'ONIE config', uuid.UUID(hex = 'D4E6E2CD-4469-46F3-B5CB-1BFF57AFC149')),
                    (10, 'Microsoft reserved', uuid.UUID(hex = 'E3C9E316-0B5C-4DB8-817D-F92DF00215AE')),
                    (11, 'Microsoft basic data', uuid.UUID(hex = 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7')),
                    (12, 'Microsoft LDM metadata', uuid.UUID(hex = '5808C8AA-7E8F-42E0-85D2-E1E90434CFB3')),
                    (13, 'Microsoft LDM data', uuid.UUID(hex = 'AF9B60A0-1431-4F62-BC68-3311714A69AD')),
                    (14, 'Windows recovery environment', uuid.UUID(hex = 'DE94BBA4-06D1-4D40-A16A-BFD50179D6AC')),
                    (15, 'IBM General Parallel Fs', uuid.UUID(hex = '37AFFC90-EF7D-4E96-91C3-2D7AE055B174')),
                    (16, 'Microsoft Storage Spaces', uuid.UUID(hex = 'E75CAF8F-F680-4CEE-AFA3-B001E56EFC2D')),
                    (17, 'HP-UX data', uuid.UUID(hex = '75894C1E-3AEB-11D3-B7C1-7B03A0000000')),
                    (18, 'HP-UX service', uuid.UUID(hex = 'E2A1E728-32E3-11D6-A682-7B03A0000000')),
                    (19, 'Linux swap', uuid.UUID(hex = '0657FD6D-A4AB-43C4-84E5-0933C84B4F4F')),
                    (20, 'Linux filesystem', uuid.UUID(hex = '0FC63DAF-8483-4772-8E79-3D69D8477DE4')),
                    (21, 'Linux server data', uuid.UUID(hex = '3B8F8425-20E0-4F3B-907F-1A25A76F98E8')),
                    (22, 'Linux root (x86)', uuid.UUID(hex = '44479540-F297-41B2-9AF7-D131D5F0458A')),
                    (23, 'Linux root (ARM)', uuid.UUID(hex = '69DAD710-2CE4-4E3C-B16C-21A1D49ABED3')),
                    (24, 'Linux root (x86-64)', uuid.UUID(hex = '4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709')),
                    (25, 'Linux root (ARM-64)', uuid.UUID(hex = 'B921B045-1DF0-41C3-AF44-4C6F280D3FAE')),
                    (26, 'Linux root (IA-64)', uuid.UUID(hex = '993D8D3D-F80E-4225-855A-9DAF8ED7EA97')),
                    (27, 'Linux reserved', uuid.UUID(hex = '8DA63339-0007-60C0-C436-083AC8230908')),
                    (28, 'Linux home', uuid.UUID(hex = '933AC7E1-2EB4-4F13-B844-0E14E2AEF915')),
                    (29, 'Linux RAID', uuid.UUID(hex = 'A19D880F-05FC-4D3B-A006-743F0F84911E')),
                    (30, 'Linux extended boot', uuid.UUID(hex = 'BC13C2FF-59E6-4262-A352-B275FD6F7172')),
                    (31, 'Linux LVM', uuid.UUID(hex = 'E6D6D379-F507-44C2-A23C-238F2A3DF928')),
                    (32, 'FreeBSD data', uuid.UUID(hex = '516E7CB4-6ECF-11D6-8FF8-00022D09712B')),
                    (33, 'FreeBSD boot', uuid.UUID(hex = '83BD6B9D-7F41-11DC-BE0B-001560B84F0F')),
                    (34, 'FreeBSD swap', uuid.UUID(hex = '516E7CB5-6ECF-11D6-8FF8-00022D09712B')),
                    (35, 'FreeBSD UFS', uuid.UUID(hex = '516E7CB6-6ECF-11D6-8FF8-00022D09712B')),
                    (36, 'FreeBSD ZFS', uuid.UUID(hex = '516E7CBA-6ECF-11D6-8FF8-00022D09712B')),
                    (37, 'FreeBSD Vinum', uuid.UUID(hex = '516E7CB8-6ECF-11D6-8FF8-00022D09712B')),
                    (38, 'Apple HFS/HFS+', uuid.UUID(hex = '48465300-0000-11AA-AA11-00306543ECAC')),
                    (39, 'Apple UFS', uuid.UUID(hex = '55465300-0000-11AA-AA11-00306543ECAC')),
                    (40, 'Apple RAID', uuid.UUID(hex = '52414944-0000-11AA-AA11-00306543ECAC')),
                    (41, 'Apple RAID offline', uuid.UUID(hex = '52414944-5F4F-11AA-AA11-00306543ECAC')),
                    (42, 'Apple boot', uuid.UUID(hex = '426F6F74-0000-11AA-AA11-00306543ECAC')),
                    (43, 'Apple label', uuid.UUID(hex = '4C616265-6C00-11AA-AA11-00306543ECAC')),
                    (44, 'Apple TV recovery', uuid.UUID(hex = '5265636F-7665-11AA-AA11-00306543ECAC')),
                    (45, 'Apple Core storage', uuid.UUID(hex = '53746F72-6167-11AA-AA11-00306543ECAC')),
                    (46, 'Solaris boot', uuid.UUID(hex = '6A82CB45-1DD2-11B2-99A6-080020736631')),
                    (47, 'Solaris root', uuid.UUID(hex = '6A85CF4D-1DD2-11B2-99A6-080020736631')),
                    (48, 'Solaris /usr & Apple ZFS', uuid.UUID(hex = '6A898CC3-1DD2-11B2-99A6-080020736631')),
                    (49, 'Solaris swap', uuid.UUID(hex = '6A87C46F-1DD2-11B2-99A6-080020736631')),
                    (50, 'Solaris backup', uuid.UUID(hex = '6A8B642B-1DD2-11B2-99A6-080020736631')),
                    (51, 'Solaris /var', uuid.UUID(hex = '6A8EF2E9-1DD2-11B2-99A6-080020736631')),
                    (52, 'Solaris /home', uuid.UUID(hex = '6A90BA39-1DD2-11B2-99A6-080020736631')),
                    (53, 'Solaris alternate sector', uuid.UUID(hex = '6A9283A5-1DD2-11B2-99A6-080020736631')),
                    (54, 'Solaris reserved 1', uuid.UUID(hex = '6A945A3B-1DD2-11B2-99A6-080020736631')),
                    (55, 'Solaris reserved 2', uuid.UUID(hex = '6A9630D1-1DD2-11B2-99A6-080020736631')),
                    (56, 'Solaris reserved 3', uuid.UUID(hex = '6A980767-1DD2-11B2-99A6-080020736631')),
                    (57, 'Solaris reserved 4', uuid.UUID(hex = '6A96237F-1DD2-11B2-99A6-080020736631')),
                    (58, 'Solaris reserved 5', uuid.UUID(hex = '6A8D2AC7-1DD2-11B2-99A6-080020736631')),
                    (59, 'NetBSD swap', uuid.UUID(hex = '49F48D32-B10E-11DC-B99B-0019D1879648')),
                    (60, 'NetBSD FFS', uuid.UUID(hex = '49F48D5A-B10E-11DC-B99B-0019D1879648')),
                    (61, 'NetBSD LFS', uuid.UUID(hex = '49F48D82-B10E-11DC-B99B-0019D1879648')),
                    (62, 'NetBSD concatenated', uuid.UUID(hex = '2DB519C4-B10E-11DC-B99B-0019D1879648')),
                    (63, 'NetBSD encrypted', uuid.UUID(hex = '2DB519EC-B10E-11DC-B99B-0019D1879648')),
                    (64, 'NetBSD RAID', uuid.UUID(hex = '49F48DAA-B10E-11DC-B99B-0019D1879648')),
                    (65, 'ChromeOS kernel', uuid.UUID(hex = 'FE3A2A5D-4F32-41A7-B725-ACCC3285A309')),
                    (66, 'ChromeOS root fs', uuid.UUID(hex = '3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC')),
                    (67, 'ChromeOS reserved', uuid.UUID(hex = '2E0A753D-9E48-43B0-8337-B15192CB1B5E')),
                    (68, 'MidnightBSD data', uuid.UUID(hex = '85D5E45A-237C-11E1-B4B3-E89A8F7FC3A7')),
                    (69, 'MidnightBSD boot', uuid.UUID(hex = '85D5E45E-237C-11E1-B4B3-E89A8F7FC3A7')),
                    (70, 'MidnightBSD swap', uuid.UUID(hex = '85D5E45B-237C-11E1-B4B3-E89A8F7FC3A7')),
                    (71, 'MidnightBSD UFS', uuid.UUID(hex = '0394EF8B-237E-11E1-B4B3-E89A8F7FC3A7')),
                    (72, 'MidnightBSD ZFS', uuid.UUID(hex = '85D5E45D-237C-11E1-B4B3-E89A8F7FC3A7')),
                    (73, 'MidnightBSD Vinum', uuid.UUID(hex = '85D5E45C-237C-11E1-B4B3-E89A8F7FC3A7')),
                    (74, 'Ceph Journal', uuid.UUID(hex = '45B0969E-9B03-4F30-B4C6-B4B80CEFF106')),
                    (75, 'Ceph Encrypted Journal', uuid.UUID(hex = '45B0969E-9B03-4F30-B4C6-5EC00CEFF106')),
                    (76, 'Ceph OSD', uuid.UUID(hex = '4FBD7E29-9D25-41B8-AFD0-062C0CEFF05D')),
                    (77, 'Ceph crypt OSD', uuid.UUID(hex = '4FBD7E29-9D25-41B8-AFD0-5EC00CEFF05D')),
                    (78, 'Ceph disk in creation', uuid.UUID(hex = '89C57F98-2FE5-4DC0-89C1-F3AD0CEFF2BE')),
                    (79, 'Ceph crypt disk in creation', uuid.UUID(hex = '89C57F98-2FE5-4DC0-89C1-5EC00CEFF2BE')),
                    (80, 'VMware VMFS', uuid.UUID(hex = 'AA31E02A-400F-11DB-9590-000C2911D1B8')),
                    (81, 'VMware Diagnostic', uuid.UUID(hex = '9D275380-40AD-11DB-BF97-000C2911D1B8')),
                    (82, 'VMware Virtual SAN', uuid.UUID(hex = '381CFCCC-7288-11E0-92EE-000C2911D0B2')),
                    (83, 'VMware Virsto', uuid.UUID(hex = '77719A0C-A4A0-11E3-A47E-000C29745A24')),
                    (84, 'VMware Reserved', uuid.UUID(hex = '9198EFFC-31C0-11DB-8F78-000C2911D1B8')),
                    (85, 'OpenBSD data', uuid.UUID(hex = '824CC7A0-36A8-11E3-890A-952519AD3F61')),
                    (86, 'QNX6 file system', uuid.UUID(hex = 'CEF5A9AD-73BC-4601-89F3-CDEEEEE321A1')),
                    (87, 'Plan 9 partition', uuid.UUID(hex = 'C91818F9-8025-47AF-89D2-F030D7000C2C')),
                    (88, 'HiFive Unleashed FSBL', uuid.UUID(hex = '5B193300-FC78-40CD-8002-E86C45580B47')),
                    (89, 'HiFive Unleashed BBL', uuid.UUID(hex = '2E54B353-1271-4842-806F-E436D6AF6985')))
# MSDOS FSTYPES IDENTIFIERS
# Second verse, same as the first - kind of. The msdos type identifers just use a byte identifier rather than UUID.
# https://git.kernel.org/pub/scm/utils/util-linux/util-linux.git/plain/include/pt-mbr-partnames.h
MSDOS_FSTYPE_IDS = ((1, 'Empty', b'\x00'),
                    (2, 'FAT12', b'\x01'),
                    (3, 'XENIX root', b'\x02'),
                    (4, 'XENIX usr', b'\x03'),
                    (5, 'FAT16 <32M', b'\x04'),
                    (6, 'Extended', b'\x05'),
                    (7, 'FAT16', b'\x06'),
                    (8, 'HPFS/NTFS/exFAT', b'\x07'),
                    (9, 'AIX', b'\x08'),
                    (10, 'AIX bootable', b'\t'),  # \x09
                    (11, 'OS/2 Boot Manager', b'\n'),  # \x0A
                    (12, 'W95 FAT32', b'\x0B'),
                    (13, 'W95 FAT32 (LBA)', b'\x0C'),
                    (14, 'W95 FAT16 (LBA)', b'\x0E'),
                    (15, "W95 Ext'd (LBA)", b'\x0F'),
                    (16, 'OPUS', b'\x10'),
                    (17, 'Hidden FAT12', b'\x11'),
                    (18, 'Compaq diagnostics', b'\x12'),
                    (19, 'Hidden FAT16 <32M', b'\x14'),
                    (20, 'Hidden FAT16', b'\x16'),
                    (21, 'Hidden HPFS/NTFS', b'\x17'),
                    (22, 'AST SmartSleep', b'\x18'),
                    (23, 'Hidden W95 FAT32', b'\x1B'),
                    (24, 'Hidden W95 FAT32 (LBA)', b'\x1C'),
                    (25, 'Hidden W95 FAT16 (LBA)', b'\x1E'),
                    (26, 'NEC DOS', b'$'),  # \x24
                    (27, 'Hidden NTFS WinRE', b"'"),  # \x27
                    (28, 'Plan 9', b'9'),  # \x39
                    (29, 'PartitionMagic recovery', b'<'),  # \x3C
                    (30, 'Venix 80286', b'@'),  # \x40
                    (31, 'PPC PReP Boot', b'A'),  # \x41
                    (32, 'SFS', b'B'),  # \x42
                    (33, 'QNX4.x', b'M'),  # \x4D
                    (34, 'QNX4.x 2nd part', b'N'),  # \x4E
                    (35, 'QNX4.x 3rd part', b'O'),  # \x4F
                    (36, 'OnTrack DM', b'P'),  # \x50
                    (37, 'OnTrack DM6 Aux1', b'Q'),  # \x51
                    (38, 'CP/M', b'R'),  # \x52
                    (39, 'OnTrack DM6 Aux3', b'S'),  # \x53
                    (40, 'OnTrackDM6', b'T'),  # \x54
                    (41, 'EZ-Drive', b'U'),  # \x55
                    (42, 'Golden Bow', b'V'),  # \x56
                    (43, 'Priam Edisk', b'\\'),  # \x5C
                    (44, 'SpeedStor', b'a'),  # \x61
                    (45, 'GNU HURD or SysV', b'c'),  # \x63
                    (46, 'Novell Netware 286', b'd'),  # \x64
                    (47, 'Novell Netware 386', b'e'),  # \x65
                    (48, 'DiskSecure Multi-Boot', b'p'),  # \x70
                    (49, 'PC/IX', b'u'),  # \x75
                    (50, 'Old Minix', b'\x80'),
                    (51, 'Minix / old Linux', b'\x81'),
                    (52, 'Linux swap / Solaris', b'\x82'),
                    (53, 'Linux', b'\x83'),
                    (54, 'OS/2 hidden or Intel hibernation', b'\x84'),
                    (55, 'Linux extended', b'\x85'),
                    (56, 'NTFS volume set', b'\x86'),
                    (57, 'NTFS volume set', b'\x87'),
                    (58, 'Linux plaintext', b'\x88'),
                    (59, 'Linux LVM', b'\x8E'),
                    (60, 'Amoeba', b'\x93'),
                    (61, 'Amoeba BBT', b'\x94'),
                    (62, 'BSD/OS', b'\x9F'),
                    (63, 'IBM Thinkpad hibernation', b'\xA0'),
                    (64, 'FreeBSD', b'\xA5'),
                    (65, 'OpenBSD', b'\xA6'),
                    (66, 'NeXTSTEP', b'\xA7'),
                    (67, 'Darwin UFS', b'\xA8'),
                    (68, 'NetBSD', b'\xA9'),
                    (69, 'Darwin boot', b'\xAB'),
                    (70, 'HFS / HFS+', b'\xAF'),
                    (71, 'BSDI fs', b'\xB7'),
                    (72, 'BSDI swap', b'\xB8'),
                    (73, 'Boot Wizard hidden', b'\xBB'),
                    (74, 'Acronis FAT32 LBA', b'\xBC'),
                    (75, 'Solaris boot', b'\xBE'),
                    (76, 'Solaris', b'\xBF'),
                    (77, 'DRDOS/sec (FAT-12)', b'\xC1'),
                    (78, 'DRDOS/sec (FAT-16 < 32M)', b'\xC4'),
                    (79, 'DRDOS/sec (FAT-16)', b'\xC6'),
                    (80, 'Syrinx', b'\xC7'),
                    (81, 'Non-FS data', b'\xDA'),
                    (82, 'CP/M / CTOS / ...', b'\xDB'),
                    (83, 'Dell Utility', b'\xDE'),
                    (84, 'BootIt', b'\xDF'),
                    (85, 'DOS access', b'\xE1'),
                    (86, 'DOS R/O', b'\xE3'),
                    (87, 'SpeedStor', b'\xE4'),
                    (88, 'Rufus alignment', b'\xEA'),
                    (89, 'BeOS fs', b'\xEB'),
                    (90, 'GPT', b'\xEE'),
                    (91, 'EFI (FAT-12/16/32)', b'\xEF'),
                    (92, 'Linux/PA-RISC boot', b'\xF0'),
                    (93, 'SpeedStor', b'\xF1'),
                    (94, 'SpeedStor', b'\xF4'),
                    (95, 'DOS secondary', b'\xF2'),
                    (96, 'VMware VMFS', b'\xFB'),
                    (97, 'VMware VMKCORE', b'\xFC'),
                    (98, 'Linux raid autodetect', b'\xFD'),
                    (99, 'LANstep', b'\xFE'),
                    (100, 'BBT', b'\xFF'))
