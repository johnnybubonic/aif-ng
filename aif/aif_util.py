def xmlBool(xmlobj):
    if isinstance(xmlobj, bool):
        return (xmlobj)
    if xmlobj.lower() in ('1', 'true'):
        return(True)
    elif xmlobj.lower() in ('0', 'false'):
        return(False)
    else:
        return(None)