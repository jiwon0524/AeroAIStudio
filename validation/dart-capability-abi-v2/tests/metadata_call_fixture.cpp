// Synthetic constraints exercise the real Boxed call path; no World::step.
#include <dart/constraint/BoxedLcpConstraintSolver.hpp>
#include <dart/constraint/BoxedLcpSolver.hpp>
#include <dart/constraint/ConstraintBase.hpp>
#include <dart/constraint/ConstrainedGroup.hpp>
#include <dart/constraint/DantzigBoxedLcpSolver.hpp>
#include <dart/constraint/PgsBoxedLcpSolver.hpp>
#ifdef TRACE_HARNESS
#include "dart/external/odelcpsolver/internal_trace.h"
#endif
#include <iostream>
#include <iomanip>
#include <limits>
#include <memory>
#include <string>
#include <vector>
using namespace dart::constraint;
static int sourceColumn=0;
static std::vector<std::string> calls;
class FixtureConstraint final:public ConstraintBase{
 int offset;
 public:std::vector<double> applied;
 explicit FixtureConstraint(int o):offset(o){mDim=2;}
 void update()override{}
 void getInformation(ConstraintInfo* p)override{for(int i=0;i<2;++i){p->b[i]=(i==0?1.:.2);p->x[i]=0;p->lo[i]=(i==0?0.:-1.);p->hi[i]=(i==0?std::numeric_limits<double>::infinity():1.);p->findex[i]=(i==0?-1:0);}}
 void applyUnitImpulse(std::size_t j)override{sourceColumn=offset+int(j);}
 void getVelocityChange(double* out,bool withCfm)override{for(int i=0;i<2;++i){out[i]=(offset+i==sourceColumn?2.:.1);if(withCfm&&offset+i==sourceColumn)out[i]*=1.00001;}}
 void excite()override{}void unexcite()override{}
 void applyImpulse(double* p)override{applied.assign(p,p+2);calls.push_back("apply"+std::to_string(offset));}
 bool isActive()const override{return true;}
 dart::dynamics::SkeletonPtr getRootSkeleton()const override{return nullptr;}
};
class FixtureSolver final:public BoxedLcpSolver{
 std::string mode,name;
 public:FixtureSolver(std::string m,std::string n):mode(std::move(m)),name(std::move(n)){}
 const std::string& getType()const override{calls.push_back("metadata:"+name);return name;}
 bool solve(int n,double*,double* x,double*,int,double*,double*,int*,bool)override{calls.push_back(name);for(int i=0;i<n;++i)x[i]=double(i+1);if(mode=="nan")x[0]=std::numeric_limits<double>::quiet_NaN();return mode!="false";}
#ifndef NDEBUG
 bool canSolve(int,const double*)override{return true;}
#endif
};
class Harness:public BoxedLcpConstraintSolver{public:using BoxedLcpConstraintSolver::solveConstrainedGroup;};
int main(int argc,char** argv){if(argc!=4)return 10;std::string mode=argv[1];bool enabled=std::string(argv[2])=="on";
#ifdef TRACE_HARNESS
 namespace tr=dart::external::ode::trace;tr::Config c;c.enabled=enabled;c.first=c.last=1;c.run="SYNTHETIC_BOXED";c.world="fixture";if(!tr::Configure(c))return 11;
#endif
 Harness solver;
 if(mode=="real_pgs_fallback"){
  solver.setBoxedLcpSolver(std::make_shared<FixtureSolver>("false","primary"));
  solver.setSecondaryBoxedLcpSolver(std::make_shared<PgsBoxedLcpSolver>());
 } else if(mode!="real_dantzig"){
  solver.setBoxedLcpSolver(std::make_shared<FixtureSolver>(mode=="primary_false"?"false":mode=="primary_nan"||mode=="nan_no_fallback"?"nan":"true","primary"));
  if(mode=="nan_no_fallback")solver.setSecondaryBoxedLcpSolver(nullptr);
  else solver.setSecondaryBoxedLcpSolver(std::make_shared<FixtureSolver>(mode=="primary_nan"?"false":"true","fallback"));
 }
 auto a=std::make_shared<FixtureConstraint>(0),b=std::make_shared<FixtureConstraint>(2);ConstrainedGroup group;group.addConstraint(a);group.addConstraint(b);
#ifdef TRACE_HARNESS
 {tr::StepScope scope((void*)1,"fixture",0,0,.001);
#endif
 solver.solveConstrainedGroup(group);
#ifdef TRACE_HARNESS
 }if(enabled&&!tr::FlushExclusive(argv[3]))return 12;
#else
 (void)enabled;
#endif
 std::cout<<std::hexfloat;for(double v:a->applied)std::cout<<v<<' ';for(double v:b->applied)std::cout<<v<<' ';std::cout<<'\n';for(const auto& s:calls)std::cout<<s<<' ';std::cout<<'\n';
}
