import subprocess
import ctypes

def getSpace():
#Get the fixed drives
#wmic logicaldisk get name,description
    drivelist = subprocess.check_output(['wmic', 'logicaldisk', 'get', 'name,description'])
    driveLines = drivelist.split('\n')
    free_space = []
    for line in driveLines:
        if line.startswith("Local Fixed Disk"):
            elements = line.split()
            driveLetter = elements[-1]
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(driveLetter), None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes))
            #print "Drive %s" % driveLetter
            #print free_bytes.value
            #print total_bytes.value
            free_space.append(str(int(float(free_bytes.value) / float(total_bytes.value) * 100.00)))
    return free_space

def divWidth():
#free space % * 2 = width of free space div
    free = getSpace()
    width = []
    
    for i in free:
        percent = (int(i))
        widthSize = (200 -(int(percent) * 2))
        width.append(str(widthSize) + 'px')
    return width
