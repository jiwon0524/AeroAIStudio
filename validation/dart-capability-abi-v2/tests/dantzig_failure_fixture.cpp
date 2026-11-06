// Intentionally invalid scalar algebra fixture, not a physical mass matrix.
#include "dart/external/odelcpsolver/lcp.h"
#ifdef TRACE_HARNESS
#include "dart/external/odelcpsolver/internal_trace.h"
#endif
#include <iostream>
#include <limits>
int main(int argc,char** argv){if(argc!=2&&argc!=3)return 10;
#ifdef TRACE_HARNESS
 namespace tr=dart::external::ode::trace;tr::Config c;c.enabled=true;c.first=c.last=1;c.run="SYNTHETIC_INVALID_LCP";c.world="fixture";if(!tr::Configure(c))return 11;
#endif
 double A[4]={-1,0,0,0},x[1]={0},b[1]={1},lo[1]={0},hi[1]={std::numeric_limits<double>::infinity()};int fi[1]={-1};bool result;
#ifdef TRACE_HARNESS
 {tr::StepScope scope((void*)1,"fixture",0,0,.001);tr::BeginAssembly(1,"invalid_fixture");
#endif
 result=dart::external::ode::dSolveLCP(1,A,x,b,nullptr,0,lo,hi,fi,argc==2);
#ifdef TRACE_HARNESS
 tr::EndAssembly();}if(!tr::FlushExclusive(argv[1]))return 12;
#endif
 std::cout<<result<<' '<<std::hexfloat<<x[0]<<'\n';
}
