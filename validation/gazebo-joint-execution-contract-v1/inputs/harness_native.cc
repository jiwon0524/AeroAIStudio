// Native resource candidate: compile/link only; never executed.
#include "native_resource.hh"
#include <tinyxml2.h>
#include "fixture.hh"
#include "exit_ack.h"
#include <gz/sim/Server.hh>
#include <gz/sim/ServerConfig.hh>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <stdexcept>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
int main(int argc, char **argv)
{
  // Fixed inherited GO pipe; never open a marker or ordinary file for GO.
  struct stat st{}, out{};
  if (argc != 3 || fstat(3, &st) != 0 || !S_ISFIFO(st.st_mode) || fstat(4,&out)!=0 || !S_ISFIFO(out.st_mode)) return 64;
  const std::filesystem::path prefix(AERO_JOINT_PREFIX);
  const auto system = std::filesystem::canonical(argv[1]);
  const auto engine = std::filesystem::canonical(argv[2]);
  const auto root = std::filesystem::canonical(prefix).string() + "/";
  if (system.string().compare(0, root.size(), root) != 0 ||
      engine.string().compare(0, root.size(), root) != 0) return 65;
  // Paths are generated locally; reject XML metacharacters before interpolation.
  if ((system.string()+engine.string()).find_first_of("&<>\"'") != std::string::npos)
    return 65;
  std::string xml=fixture_sdf;
  const auto substitute=[&](const char *token,const std::string &value) {
    auto at=xml.find(token); if(at==std::string::npos) throw std::runtime_error("fixture token missing");
    xml.replace(at,std::string(token).size(),value);
  };
  substitute("@SYSTEM@",system.string()); substitute("@ENGINE@",engine.string());
  #include "plugin_expectations.hh"
  const auto configBytes = aero_resource::Config();
  tinyxml2::XMLDocument configXml;
  const bool configOk = configXml.Parse(configBytes.data(), configBytes.size()) == tinyxml2::XML_SUCCESS;
  auto *configRoot = configXml.RootElement();
  aero_resource::Outcome("server_config_parse", configOk && configRoot &&
      std::string(configRoot->Name()) == "server_config" && !configRoot->FirstChildElement(), configOk ? 0 : 1);
  gz::sim::ServerConfig config;
  if (!config.SetSdfString(xml)) return 66;
  config.SetUseLevels(false);
  config.SetInitialSimTime(0.0);
  config.SetPhysicsEngine(engine.string());
  gz::sim::Server server(config);
  const auto before=server.IterationCount();
  if(!before || *before!=0) return 68;
  if(!server.Run(true,100,false)) return 67;
  const auto after=server.IterationCount();
  if(!after || *after!=100) return 69;
  // Keep Server and all native/plugin owners alive until final mapping ACK.
  if(!aero_exit_barrier()) return 70;
  return 0;
}
