# FFT class 
# Written by Marko Kosunen, marko.kosunen@aalto.fi, 05.03.2019 11:07
import os
import sys

import numpy as np

from thesdk import *
from verilog import *
from verilog.testbench import *
from verilog.testbench import testbench as vtb

class FFT(verilog,thesdk):
    @property
    def _classfile(self):
        return os.path.dirname(os.path.realpath(__file__)) + "/"+__name__

    def __init__(self,*arg): 
        self.proplist = [ 'Rs', 'FFT_N' ]; #properties that can be propagated from parent
        self.Rs = 160e6;                   # Sampling frequency
        self.FFT_N  = 64;                  # Npoint FFT
        self.io_in = IO();                 # Pointer for input data
        self.model='py';                   # Can be set externally, but is not propagated
        self.par= False;                   # By default, no parallel processing
        self.queue= [];                    # By default, no parallel processing
        self._io_out = IO();               # Pointer for output data
        self.control_in = IO();            # IO, with property Data
        self.control_in.Data = Bundle()    # Bundle of verilog_iofiles, inited empty
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
        self.vlogparameters=dict([ ('g_Rs',self.Rs),])

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
          if self.model=='sv':
              if not 'control_file' in self.control_in.Data.Members:
                  self.create_controlfile()
                  self.reset_sequence()
              else:
                  self.control_in.Data.Members['control_file'].adopt(parent=self)

              # Create testbench and execute the simulation
              self.define_testbench()
              self.tb.export(force=True)
              self.write_infile()
              self.run_verilog()
              self.read_outfile()
              del self.iofile_bundle

          elif self.model=='vhdl':
              self.print_log(type='F', msg='VHDL model not yet supported')

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
        if self.par:
            self.queue.put(self._io_out)

    def create_controlfile(self):
        self.control_in.Data.Members['control_file']=verilog_iofile(self,
            name='control_file',
            dir='in',
            iotype='ctrl'
        )
        # Create connectors of the signals controlled by this file
        # Connector list simpler to create with intermediate variable
        c=verilog_connector_bundle()
        c.new(name='reset', cls='reg')
        c.new(name='initdone', cls='reg')
        self.control_in.Data.Members['control_file']\
                .verilog_connectors=c.list(names=[ 'initdone', 'reset'])
        print(self.control_in.Data.Members['control_file'].verilog_connectors[1].name)

    def reset_sequence(self):
        #start defining the file
        f=self.control_in.Data.Members['control_file']
        f.set_control_data(init=0) #Initialize to zero at time 0
        time=0
        for name in [ 'reset', ]:
            f.set_control_data(time=time,name=name,val=1)

        # After awhile, switch off reset 
        time=int(16/(self.Rs*1e-12))

        for name in [ 'reset', ]:
            f.set_control_data(time=time,name=name,val=0)
        for name in [ 'initdone', ]:
            f.set_control_data(time=time,name=name,val=1)

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

        # Create TB connectors from the control file
        for connector in self.control_in.Data.Members['control_file'].verilog_connectors:
            self.tb.connectors.Members[connector.name]=connector
            # Connect them to DUT
            try: 
                self.dut.ios.Members[connector.name].connect=connector
            except:
                pass

        ## Start initializations
        #Init the signals connected to the dut input to zero
        for name, val in self.tb.dut_instance.ios.Members.items():
            if val.cls=='input':
                val.connect.init='\'b0'

        self.tb.connectors.init(match=r"io_in_valid",init='\'b1')
        # Connect one of the Dut inputs to clock and de-init it
        self.tb.connectors.connect(match=r"io_in_sync",connect='clock')
        self.tb.connectors.init(match=r"io_in_sync",init='')

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

        self.generate_tb_contents()
        
    def generate_tb_contents(self):
    # Start the testbench contents
        self.tb.contents="""
//timescale 1ps this should probably be a global model parameter
parameter integer c_Ts=1/(g_Rs*1e-12);
reg done;
"""+\
self.tb.connector_definitions+\
self.tb.assignments(matchlist=[r"io_in_sync"])+\
self.tb.iofile_definitions+\
"""

//DUT definition
"""+\
self.tb.dut_instance.instance+\
"""

//Master clock is omnipresent
always #(c_Ts/2.0) clock = !clock;

//Execution with parallel fork-join and sequential begin-end sections
initial #0 begin
fork
done=0;
""" + \
self.tb.connectors.verilog_inits(level=1)+\
"""
//io_out
$display("Ready to write");
@(posedge initdone) begin
    $display("Posedge initdone");
while (!done) begin
@(posedge clock ) begin
    //Print only valid values
    if ("""+\
            self.iofile_bundle.Members['io_out'].verilog_io_condition +\
        """) begin
        """+\
            self.iofile_bundle.Members['io_out'].verilog_io+\
        """
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
             """+\
             self.iofile_bundle.Members['io_in'].verilog_io+\
             """
        end
        done<=1;
    end
begin
"""+\
self.iofile_bundle.Members['control_file'].verilog_io+\
"""
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
    dut.run()
    dut2.run()
    plt.figure(0)
    plt.plot(np.abs(dut._io_out.Data[10,:]))
    plt.suptitle("Python model")
    plt.xlabel("Freq")
    plt.ylabel("Abs(FFT)")
    plt.show(block=False)
    plt.figure(1)
    plt.plot(np.abs(dut2._io_out.Data[10,:]))
    plt.suptitle("Verilog model")
    plt.xlabel("Freq")
    plt.ylabel("Abs(FFT)")
    plt.show(block=False)
    input()


