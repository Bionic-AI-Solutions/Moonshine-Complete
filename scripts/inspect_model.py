import os
p = r"E:\Bionic AI\moonshine\moonshine-streaming-medium"
if not os.path.exists(p):
    print('MISSING')
else:
    files=[]
    for root,_,fnames in os.walk(p):
        for f in fnames:
            fp=os.path.join(root,f)
            try:
                sz=os.path.getsize(fp)
            except OSError:
                sz=0
            files.append((sz,fp))
    files.sort(reverse=True)
    for sz,fp in files[:20]:
        print(f"{sz/1024/1024:.2f} MB\t{fp}")
    total=sum(sz for sz,_ in files)
    print('---TOTAL---')
    print(f"{total/1024/1024:.2f} MB total")
