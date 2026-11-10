#include "native_resource.hh"
#include "identities.hh"
#include "bound.h"
#include <openssl/sha.h>
#include <sys/stat.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <mutex>
#include <map>
#include <set>
#include <stdexcept>
#include <cstdio>
#include <cerrno>
#include <cstring>
namespace aero_resource {
namespace {
std::recursive_mutex mu;
bool failed=false, sealed=false;
unsigned sequence=0;
unsigned schemaReads=0, schemaInits=0, schemaIncludes=0;
std::set<std::string> emitted;
struct Identity { std::string path, hash; uint64_t dev, ino; };
std::map<std::string,Identity> plugins;
std::set<std::string> loaded, outcomes;
std::string hash(const std::string &s) {
 unsigned char digest[SHA256_DIGEST_LENGTH]; SHA256((const unsigned char*)s.data(),s.size(),digest);
 char result[65]; for(unsigned i=0;i<32;++i) std::snprintf(result+2*i,3,"%02x",digest[i]); return result;
}
// Fields in this channel are fixed identifiers, hex hashes and integer values.
void event(const char *role,const char *sha,uint64_t dev,uint64_t ino,bool ok) {
 char packet[512];
 int length=std::snprintf(packet,sizeof(packet),"{\"kind\":\"native_resource\",\"seq\":%u,\"role\":\"%s\",\"sha256\":\"%s\",\"device\":%llu,\"inode\":%llu,\"ok\":%s}\n",
 ++sequence,role,sha,(unsigned long long)dev,(unsigned long long)ino,ok?"true":"false");
 if(length<0||size_t(length)>=sizeof(packet)) {failed=true;throw std::runtime_error("resource packet bound");}
 ssize_t written;do {written=::write(4,packet,length);} while(written<0&&errno==EINTR);
 if(written!=length) {failed=true;throw std::runtime_error("resource observation write failed");}
}
std::string read(const Identity &id,const char *role) {
 if(failed || sealed) Fail("resource access after seal/failure");
 int fd=::open(id.path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
 if(fd<0) Fail("required resource open failed");
 struct stat a{},b{};
 struct bound copied{};
 if(bound_verify(fd,id.hash.c_str(),nullptr,&copied)||fstat(fd,&a)||!S_ISREG(a.st_mode)||uint64_t(a.st_dev)!=copied.dev||uint64_t(a.st_ino)!=copied.ino||a.st_size<0||a.st_size>128*1024*1024) {close(fd);Fail("required FD identity mismatch");}
 std::string bytes; char chunk[16384]; ssize_t n;
 while((n=::read(fd,chunk,sizeof(chunk)))>0) {bytes.append(chunk,n);if(bytes.size()>128*1024*1024){close(fd);Fail("resource size bound");}}
 const bool stable=n==0 && !fstat(fd,&b) && a.st_size==b.st_size && a.st_mtim.tv_sec==b.st_mtim.tv_sec && a.st_mtim.tv_nsec==b.st_mtim.tv_nsec && a.st_ctim.tv_sec==b.st_ctim.tv_sec && a.st_ctim.tv_nsec==b.st_ctim.tv_nsec;
 close(fd);
 const auto digest=hash(bytes);
 if(!stable || bytes.size()!=size_t(a.st_size) || digest!=id.hash) Fail("required FD bytes mismatch");
 if(std::string(role).rfind("schema/",0)==0) ++schemaReads;
 if(emitted.insert(role).second) event(role,digest.c_str(),a.st_dev,a.st_ino,true); return bytes;
}
std::string spec(const std::string &name) {
 for(const auto &id: identities) if(name==id.name) return read({id.path,id.hash,id.dev,id.ino},id.name);
 Fail("unapproved schema/conversion name"); return {};
}
}
void Fail(const char *reason) {
 std::lock_guard<std::recursive_mutex> lock(mu); failed=true;
 event("fatal","",0,0,false); throw std::runtime_error(reason);
}
std::string Schema(const std::string &name) {
 std::lock_guard<std::recursive_mutex> lock(mu);return spec("schema/"+name);
}
std::string Conversion(const std::string &name) {
 std::lock_guard<std::recursive_mutex> lock(mu);return spec("conversion/"+name);
}
void Outcome(const char *role,bool ok,std::size_t errors) {
 std::lock_guard<std::recursive_mutex> lock(mu);
 if(failed||sealed||!ok||errors) Fail("native parse/init/graph failure");
 if(std::string(role)=="schema_init") ++schemaInits;
 if(std::string(role)=="schema_include") ++schemaIncludes;
 if(outcomes.insert(role).second) event(role,"",0,0,true);
}
std::string Config() {std::lock_guard<std::recursive_mutex> lock(mu);return spec("server_config");}
void World(const std::string &bytes) {
 std::lock_guard<std::recursive_mutex> lock(mu);
 if(failed||sealed||hash(bytes)!=world_sha256) Fail("actual world input differs");
 event("world_bytes",hash(bytes).c_str(),0,0,true);
}
void Expect(const char *role,const char *path,uint64_t dev,uint64_t ino,const char *sha) {
 std::lock_guard<std::recursive_mutex> lock(mu);
 if(failed||sealed||!plugins.emplace(role,Identity{path,sha,dev,ino}).second) Fail("duplicate plugin expectation");
}
void BeforeLoad(const char *role,const std::string &request,const std::string &selected,const std::string &klass) {
 std::lock_guard<std::recursive_mutex> lock(mu);
 // Check seal before opening, resolving or invoking the plugin loader.
 if(failed||sealed) Fail("late load request denied");
 auto it=plugins.find(role);
 if(it==plugins.end()||request!=it->second.path||selected!=it->second.path||loaded.count(role)||klass.empty()) Fail("plugin selection/fallback rejected");
 read(it->second,role);
}
void Provider(const char *role,const void *object) {
 // Pinned x86_64 Itanium C++ ABI: interface subobject starts with its vptr.
 const void *vtable=nullptr; if(object) std::memcpy(&vtable,object,sizeof(vtable));
 std::lock_guard<std::recursive_mutex> lock(mu);
 Dl_info info{}; auto it=plugins.find(role);
 if(failed||sealed||it==plugins.end()||!vtable||!dladdr(vtable,&info)||!info.dli_fname||it->second.path!=info.dli_fname) Fail("loaded provider mismatch");
 int providerFd=::open(it->second.path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 struct bound providerCopy{};
 if(providerFd<0) Fail("provider FD missing");
 if(bound_verify(providerFd,it->second.hash.c_str(),nullptr,&providerCopy)||bound_anchor(vtable,providerFd)) {
   close(providerFd);Fail("provider mapping differs from final sealed FD");
 }
 close(providerFd);
 read(it->second,(std::string(role)+"_provider").c_str());
}
void Loaded(const char *role,bool ok) {
 std::lock_guard<std::recursive_mutex> lock(mu);
 if(failed||sealed||!ok||!plugins.count(role)||!loaded.insert(role).second) Fail("plugin load/interface failure");
 event((std::string(role)+"_loaded").c_str(),"",0,0,true);
}
void CheckLoadRequest() {std::lock_guard<std::recursive_mutex> lock(mu);if(failed||sealed) Fail("late load request denied before lookup/open");}
void NoMoreLoads() {std::lock_guard<std::recursive_mutex> lock(mu);sealed=true;}
void Ready() {
 std::lock_guard<std::recursive_mutex> lock(mu);
 if(!schemaReads||schemaInits<schemaReads||schemaIncludes<schemaReads-1) Fail("incomplete native recursive schema results");
 if(failed||!sealed||loaded!=std::set<std::string>{"physics","dartsim"}||!outcomes.count("server_config_parse")||!outcomes.count("schema_root")||!outcomes.count("world_parse")||!outcomes.count("world_graph")) Fail("missing native pre-GO outcome");
 event("complete","",0,0,true);
}
}
