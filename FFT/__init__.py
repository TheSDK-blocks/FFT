# FFT class 
# Last modification by Marko Kosunen, marko.kosunen@aalto.fi, 05.01.2018 11:07
#Add TheSDK to path. Importing it first adds the rest of the modules
#Simple buffer template
import os
import sys

import numpy as np
import tempfile

from thesdk import *
from verilog import *

class FFT(verilog,vhdl,thesdk):
    def __init__(self,*arg): 
        self.proplist = [ 'Rs' ];    #properties that can be propagated from parent
        self.Rs = 1;                 # sampling frequency
        self.iptr_A = refptr();      # Pointer for input data
        self.model='py';             #can be set externally, but is not propagated
        self.par= False              #By default, no parallel processing
        self.queue= []               #By default, no parallel processing
        self._Z = refptr();          # Pointer for output data
        #Classfile is required by verilog and vhdl classes to determine paths.
        self._classfile=os.path.dirname(os.path.realpath(__file__)) + "/"+__name__
        if len(arg)>=1:
            parent=arg[0]
            self.copy_propval(parent,self.proplist)
            self.parent =parent;
        self.init()
    def init(self):
        self._vlogparameters =dict([('Rs',100e6)])
        self.def_verilog()
        self._vhdlparameters =dict([('Rs',100e6)])
        self.def_vhdl()

    def main(self):
        out=np.array(self.iptr_A.Value)
        if self.par:
            self.queue.put(out)
        self._Z.Value=out

    def run(self,*arg):
        if len(arg)>0:
            self.par=True      #flag for parallel processing
            self.queue=arg[0]  #multiprocessing.queue as the first argument
        if self.model=='py':
            self.main()
        else: 
          self.write_infile()
          if self.model=='sv':
              self.run_verilog()
          elif self.model=='vhdl':
              self.run_vhdl()
          self.read_outfile()

    def write_infile(self):
        rndpart=os.path.basename(tempfile.mkstemp()[1])
        if self.model=='sv':
            self._infile=self._vlogsimpath +'/A_' + rndpart +'.txt'
            self._outfile=self._vlogsimpath +'/Z_' + rndpart +'.txt'
        elif self.model=='vhdl':
            self._infile=self._vhdlsimpath +'/A_' + rndpart +'.txt'
            self._outfile=self._vhdlsimpath +'/Z_' + rndpart +'.txt'
        else:
            pass
        try:
          os.remove(self._infile)
        except:
          pass
        fid=open(self._infile,'wb')
        np.savetxt(fid,np.transpose(self.iptr_A.Value),fmt='%.0f')
        #np.savetxt(fid,self.iptr_A.Value.reshape(-1,1).view(float),fmt='%i', delimiter='\t')
        fid.close()

    def read_outfile(self):
        fid=open(self._outfile,'r')
        out = np.transpose(np.loadtxt(fid))
        #out = np.loadtxt(fid,dtype=complex)
        #Of course it does not work symmetrically with savetxt
        #out=(out[:,0]+1j*out[:,1]).reshape(-1,1) 
        fid.close()
        os.remove(self._outfile)
        if self.par:
            self.queue.put(out)
        self._Z.Value=out

if __name__=="__main__":
    import matplotlib.pyplot as plt
    from  FFT import *
    t=thesdk()
    t.print_log({'type':'I', 'msg': "This is a testing template. Enjoy"})
