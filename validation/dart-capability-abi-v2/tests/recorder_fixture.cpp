#include "dart/external/odelcpsolver/internal_trace.h"
#include <stdexcept>
#include <thread>
#include <cstring>
#include <iostream>
#include <limits>
using namespace dart::external::ode;
int main(int argc,char**argv){
 if(argc!=3)return 10;
 const char* mode=argv[1];trace::Config c;c.enabled=true;c.first=10;c.last=14;c.run="SYNTHETIC_FIXTURE";c.world="synthetic";
 if(!std::strcmp(mode,"disabled")){trace::BeginStep((void*)1,"synthetic",9,.009,.001);if(trace::GetStatus().records)return 11;if(trace::FlushExclusive(argv[2]))return 12;return 0;}
 if(!std::strcmp(mode,"bad_config")){c.last=15;return trace::Configure(c)?13:0;}
 if(!std::strcmp(mode,"overflow"))c.values=4;
 if(!trace::Configure(c))return 14;
 if(!std::strcmp(mode,"thread")){std::thread t([]{trace::BeginStep((void*)1,"synthetic",9,.009,.001);});t.join();}
 else for(int frame=9;frame<14;++frame){
  if(!std::strcmp(mode,"gap")&&frame==10)continue;
  try{
   trace::StepScope scope((void*)1,!std::strcmp(mode,"wrong_world")?"other":"synthetic",frame,frame*.001,.001);
   if(!std::strcmp(mode,"nested")){trace::StepScope inner((void*)1,"synthetic",frame,frame*.001,.001);}
   if(!std::strcmp(mode,"interrupted"))throw std::runtime_error("fixture exception");
   trace::BeginAssembly(2,"fixture_solver");trace::SetRow(0,0,2);
   double a[]={2.,.25,999.,998.,.25,3.,997.,996.};
   trace::Matrix("A0","synthetic_fixture",a,2,!std::strcmp(mode,"bad_stride")?1:4);
   double b[]={1.,2.},x[]={0.,0.},lo[]={0.,-std::numeric_limits<double>::infinity()},hi[]={std::numeric_limits<double>::infinity(),1.};int fi[]={-1,0};
   trace::Emit("b0","synthetic_fixture","velocity",b,2);trace::Emit("x0","synthetic_fixture","impulse",x,2);trace::Emit("lo0","synthetic_fixture","bounds",lo,2);trace::Emit("hi0","synthetic_fixture","bounds",hi,2);trace::Integers("findex0","synthetic_fixture",fi,2);
   trace::Scalar("primary_raw_return","synthetic_fixture",1);trace::Scalar("fallback_called","synthetic_fixture",0);trace::Emit("final_x","synthetic_fixture","row_impulse",b,2);
   double bits[]={-0.,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()};trace::Emit("special_bits","synthetic_fixture","IEEE754",bits,3);
   a[0]=123;b[0]=456;trace::EndAssembly();
  }catch(const std::runtime_error& e){if(std::strcmp(e.what(),"fixture exception"))return 15;}
 }
 bool saved=trace::FlushExclusive(argv[2]);
 auto st=trace::GetStatus();std::cout<<saved<<' '<<st.faults<<' '<<st.steps<<' '<<st.records<<'\n';
 return 0;
}
