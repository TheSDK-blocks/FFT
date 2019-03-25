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
from verilog.testbench import *
from verilog.testbench import testbench as vtb

class FFT(verilog,thesdk):
    @property
    def _classfile(self):
        return os.path.dirname(os.path.realpath(__file__)) + "/"+__name__

    def __init__(self,*arg): 
        self.proplist = [ 'Rs', 'FFT_N' ];    #properties that can be propagated from parent
        self.Rs = 160e6;                 # Ssampling frequency
        self.FFT_N  = 64;            # Npoint FFT
        self.io_in = IO();           # Pointer for input data
        self.model='py';             # Ccan be set externally, but is not propagated
        self.par= False;             # By default, no parallel processing
        self.queue= [];              # By default, no parallel processing
        self._io_out = IO();         # Pointer for output data
        if len(arg)>=1:
            parent=arg[0]
            self.copy_propval(parent,self.proplist)
            self.parent =parent;
        self.init()
    def init(self):
        #This gets updated every time you add an iofile
        self.iofile_bundle=Bundle()
        #Adds files to bundle
        _=verilog_iofile(self,name='io_out',datatype='complex')
        _=verilog_iofile(self,name='io_in',dir='in')
        #self.vlogmodulefiles =list(['clkdiv_n_2_4_8.v', 'AsyncResetReg.v'])
        self.vlogparameters=dict([ ('g_Rs',self.Rs), 
            ])

    def main(self):
        out=np.array(np.fft.fft(self.io_in.Data,self.FFT_N,1)) #FFT on colum, row is time
        if self.par:
            self.queue.put(out)
        self._io_out.Data=out

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
        #Input file data definitions
        indata=self.io_in.Data
        self.iofile_bundle.Members['io_in'].data=indata
        indata=None #Clear variable to save memory

        # This could be a method somewhere
        for name, val in self.iofile_bundle.Members.items():
            if val.dir=='in':
                self.iofile_bundle.Members[name].write()

    def read_outfile(self):
        #Handle the ofiles here as you see the best
        a=self.iofile_bundle.Members['io_out']
        a.read(dtype='object')
        self._io_out.Data=a.data
        print(self._io_out.Data)
        self.distribute_result()

    def distribute_result(self):
        if self.par:
            self.queue.put(self._io_out)
     
    #Define method that generates reset sequence verilog
    def reset_sequence(self):
    #    reset_sequence='begin\n'+self.iofile_bundle.Members['scan_inputs'].verilog_io+"""
#end"""
        reset_sequence="""
        begin
            done=0;
            reset=1;
            #(16*c_Ts)
            reset=0;
            io_in_valid=1;
            initdone=1;
        end
        """
        return reset_sequence

    # Testbench definition method
    def define_testbench(self):
        #Initialize testbench
        self.tb=vtb(self)
        # Dut is creted automaticaly, if verilog file for it exists
        self.tb.connectors.update(bundle=self.tb.dut_instance.io_signals.Members)

        #Assign verilog simulation parameters to testbench
        self.tb.parameters=self.vlogparameters

        # Copy iofile simulation parameters to testbench
        for name, val in self.iofile_bundle.Members.items():
            self.tb.parameters.Members.update(val.vlogparam)

        # Define the iofiles of the testbench. '
        # Needed for creating file io routines 
        self.tb.iofiles=self.iofile_bundle

        #Define testbench verilog file
        self.tb.file=self.vlogtbsrc


        #for connector in self.scan.Data.Members['scan_inputs'].verilog_connectors:
        #    self.tb.connectors.Members[connector.name]=connector
        #    try: 
        #        self.dut.ios.Members[connector.name].connect=connector
        #    except:
        #        pass

        #    try: 
        #        clkdivider.ios.Members[connector.name].connect=connector
        #    except:
        #        pass

        # Some signals needed to control the sim
        #self.tb.connectors.new(name='reset_loop', cls='reg')
        #self.tb.connectors.new(name='asyncResetIn_clockRef', cls='reg') #Redundant?
        #self.tb.connectors.new(name='lane_clkrst_asyncResetIn', cls='reg') #Redundant?
        self.tb.connectors.connect(match=r"io_in_sync",connect='clock')


        ## Start initializations
        #Init the signals connected to the dut input to zero
        for name, val in self.tb.dut_instance.ios.Members.items():
            if val.cls=='input':
                val.connect.init='\'b0'

        ## Some to ones
        #oneslist=[
        #    'asyncResetIn_clockRef',
        #    'lane_clkrst_asyncResetIn',
        #    'io_ctrl_and_clocks_reset_index_count', #%Is this obsoleted?
        #    ]
        #These are driven by serdeses, and serdes models are not there

        # IO file connector definitions
        # Define what signals and in which order and format are read form the files
        # i.e. verilog_connectors of the file
        name='io_out'
        ionames=[]
        for count in range(self.FFT_N):
            ionames+=[ 'io_out_bits_%s_real' %(count), 'io_out_bits_%s_imag' %(count)]
        self.iofile_bundle.Members[name].verilog_connectors=\
                self.tb.connectors.list(names=ionames)
        for name in ionames:
            self.tb.connectors.Members[name].type='signed'

        name='io_in'
        ionames=[]
        for count in range(self.FFT_N):
            ionames+=['io_in_bits_%s_real' %(count),
                     'io_in_bits_%s_imag' %(count)]
        self.iofile_bundle.Members[name].verilog_connectors=\
                self.tb.connectors.list(names=ionames)
        
        # This should be a method too
        # Start the testbench contents
        self.tb.contents="""
//timescale 1ps this should probably be a global model parameter
parameter integer c_Ts=1/(g_Rs*1e-12);
reg initdone;
reg done;
"""+ self.tb.connector_definitions+self.tb.iofile_definitions+"""


//DUT definition
"""+self.tb.dut_instance.instance+"""

//Master clock is omnipresent
always #(c_Ts/2.0) clock = !clock;

//Execution with parallel fork-join and sequential begin-end sections
initial #0 begin
initdone=0;
""" + self.tb.connectors.verilog_inits(level=1)+"""
fork""" +self.reset_sequence()+""" 
//io_out
$display("Ready to write");
@(posedge initdone) begin
    $display("Posedge initdone");
while (!done) begin
@(posedge clock ) begin
    //Print only valid values
    if ("""+self.iofile_bundle.Members['io_out'].verilog_io_condition + """
    ) begin \n"""+ self.iofile_bundle.Members['io_out'].verilog_io+"""
     end
end
end
end

        // Sequence triggered by initdone
        $display("Ready to read");
        @(posedge initdone ) begin
        $display("Posedge initdone");
            while (!$feof(f_io_in)) begin
                 @(posedge clock )
                 """+ self.iofile_bundle.Members['io_in'].verilog_io+"""
            end
            done<=1;
        end
    join
    """+self.tb.iofile_close+"""
    $finish;
end"""

if __name__=="__main__":
    import matplotlib.pyplot as plt
    from  FFT import *
    dut=FFT()
    dut2=FFT()
    dut.model='py'
    dut2.model='sv'
    #dut2.interactive_verilog=True
    len=16*64
    phres=64
    fsig=25e6
    indata=2**10*np.exp(1j*2*np.pi/phres*(np.arange(len)*np.round(fsig/dut.Rs*phres)))\
            .reshape(-1,64)
    dut.io_in.Data=indata
    dut2.io_in.Data=indata
    dut2.define_testbench()
    dut2.tb.export(force=True)
    dut.run()
    dut2.run()
    plt.figure(0)
    plt.plot(np.abs(dut._io_out.Data[10,:]))
    plt.suptitle("Python model")
    plt.show(block=False)
    plt.figure(1)
    plt.plot(np.abs(dut2._io_out.Data[10,:]))
    plt.suptitle("Verilog model")
    plt.show(block=False)
    input()


