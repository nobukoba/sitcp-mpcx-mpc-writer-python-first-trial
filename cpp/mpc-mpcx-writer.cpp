#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <netdb.h>
#include <stdexcept>
#include <string>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>
#include <algorithm>

namespace {
constexpr double DEFAULT_TIMEOUT = 3.0;
constexpr uint16_t DEFAULT_PORT = 4660;
constexpr uint32_t EEPROM_BASE = 0xFFFFFC00u;
constexpr uint32_t EEPROM_WRITE_ENABLE = 0xFFFFFCFFu;
constexpr uint32_t XG_PROBE_ADDRESS = 0xFFFFFF50u;
constexpr size_t EEPROM_READ_SIZE = 0x50;
constexpr size_t MPC_FILE_SIZE = 22;
constexpr int FIELD_WIDTH = 20;

struct RbcpError : std::runtime_error { using std::runtime_error::runtime_error; };
struct RbcpTimeout : RbcpError { using RbcpError::RbcpError; };
struct RbcpBusError : RbcpError { using RbcpError::RbcpError; };

std::string hex_bytes(const std::vector<uint8_t>& data, size_t begin=0, size_t end=SIZE_MAX, char sep=' ') {
    end = std::min(end, data.size());
    std::ostringstream os;
    os << std::hex << std::setfill('0');
    for (size_t i=begin;i<end;++i) {
        if (i>begin) os << sep;
        os << std::setw(2) << static_cast<unsigned>(data[i]);
    }
    return os.str();
}

void field(const std::string& key, const std::string& value) {
    std::cout << std::left << std::setw(FIELD_WIDTH) << key << ": " << value << "\n";
}

class RbcpClient {
public:
    RbcpClient(std::string host, uint16_t port, double timeout)
        : host_(std::move(host)), port_(port), timeout_(timeout) {}

    std::vector<uint8_t> read(uint32_t address, size_t length) {
        if (length > 255) throw RbcpError("one RBCP read is limited to 255 bytes");
        const uint8_t id = next_id();
        auto packet = header(0xC0, address, static_cast<uint8_t>(length), id);
        return transaction(packet, id);
    }

    std::vector<uint8_t> write(uint32_t address, const std::vector<uint8_t>& data) {
        if (data.size() > 255) throw RbcpError("one RBCP write is limited to 255 bytes");
        const uint8_t id = next_id();
        auto packet = header(0x80, address, static_cast<uint8_t>(data.size()), id);
        packet.insert(packet.end(), data.begin(), data.end());
        return transaction(packet, id);
    }

private:
    uint8_t next_id() { uint8_t v = packet_id_; packet_id_ = static_cast<uint8_t>(packet_id_ + 1); return v; }

    static std::vector<uint8_t> header(uint8_t cmd, uint32_t addr, uint8_t len, uint8_t id) {
        return {0xFF, cmd, id, len,
                static_cast<uint8_t>((addr >> 24) & 0xFF),
                static_cast<uint8_t>((addr >> 16) & 0xFF),
                static_cast<uint8_t>((addr >> 8) & 0xFF),
                static_cast<uint8_t>(addr & 0xFF)};
    }

    std::vector<uint8_t> transaction(const std::vector<uint8_t>& packet, uint8_t id) {
        addrinfo hints{}; hints.ai_family = AF_INET; hints.ai_socktype = SOCK_DGRAM;
        addrinfo* res = nullptr;
        const std::string portstr = std::to_string(port_);
        int gai = getaddrinfo(host_.c_str(), portstr.c_str(), &hints, &res);
        if (gai != 0) throw RbcpError(std::string("getaddrinfo: ") + gai_strerror(gai));

        int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
        if (fd < 0) { freeaddrinfo(res); throw RbcpError(std::string("socket: ") + std::strerror(errno)); }

        ssize_t sent = sendto(fd, packet.data(), packet.size(), 0, res->ai_addr, res->ai_addrlen);
        freeaddrinfo(res);
        if (sent != static_cast<ssize_t>(packet.size())) { close(fd); throw RbcpError(std::string("sendto: ") + std::strerror(errno)); }

        fd_set rfds; FD_ZERO(&rfds); FD_SET(fd, &rfds);
        timeval tv{};
        tv.tv_sec = static_cast<long>(timeout_);
        tv.tv_usec = static_cast<long>((timeout_ - tv.tv_sec) * 1'000'000.0);
        int rv = select(fd + 1, &rfds, nullptr, nullptr, &tv);
        if (rv == 0) { close(fd); throw RbcpTimeout("RBCP timeout from " + host_ + ":" + std::to_string(port_)); }
        if (rv < 0) { close(fd); throw RbcpError(std::string("select: ") + std::strerror(errno)); }

        uint8_t buf[263];
        ssize_t n = recvfrom(fd, buf, sizeof(buf), 0, nullptr, nullptr);
        close(fd);
        if (n < 0) throw RbcpError(std::string("recvfrom: ") + std::strerror(errno));
        if (n < 8) throw RbcpError("short RBCP reply: " + std::to_string(n) + " bytes");
        if (buf[0] != 0xFF) throw RbcpError("unexpected RBCP version/type");
        if (buf[2] != id) throw RbcpError("packet ID mismatch");
        if (buf[1] & 0x01) throw RbcpBusError("RBCP bus error returned by target");
        return std::vector<uint8_t>(buf + 8, buf + n);
    }

    std::string host_;
    uint16_t port_;
    double timeout_;
    uint8_t packet_id_ = 0;
};

std::vector<uint8_t> read_retry(RbcpClient& c, uint32_t addr, size_t len, int attempts=3) {
    for (int i=0;i<attempts;++i) {
        try { return c.read(addr, len); }
        catch (const RbcpTimeout&) { if (i+1==attempts) throw; }
    }
    throw RbcpTimeout("RBCP timeout");
}

std::vector<uint8_t> read_exact(RbcpClient& c, uint32_t addr, size_t len, size_t chunk=8) {
    std::vector<uint8_t> out;
    for (size_t off=0; off<len; off+=chunk) {
        size_t n = std::min(chunk, len-off);
        auto b = read_retry(c, addr + static_cast<uint32_t>(off), n);
        if (b.size()!=n) throw RbcpError("short EEPROM read");
        out.insert(out.end(), b.begin(), b.end());
    }
    return out;
}

void write_exact(RbcpClient& c, uint32_t addr, const std::vector<uint8_t>& data, size_t chunk=16) {
    for (size_t off=0; off<data.size(); off+=chunk) {
        size_t n=std::min(chunk, data.size()-off);
        std::vector<uint8_t> block(data.begin()+off, data.begin()+off+n);
        auto ack=c.write(addr+static_cast<uint32_t>(off), block);
        if (ack.size()!=n) throw RbcpError("short RBCP ACK while writing EEPROM");
    }
}

bool valid_tag(const std::vector<uint8_t>& b) {
    if (b.size()!=7) return false;
    for (uint8_t x:b) {
        if (x==0 || x==0x20 || x=='-') continue;
        if (x>='0'&&x<='9') continue;
        uint8_t u=static_cast<uint8_t>(x & 0xDF);
        if (u>='A'&&u<='Z') continue;
        return false;
    }
    return true;
}

std::vector<uint8_t> decode_nonzero(const std::vector<uint8_t>& d,size_t begin,size_t len,uint8_t delta) {
    std::vector<uint8_t> out; out.reserve(len);
    for(size_t i=0;i<len;++i){uint8_t b=d[begin+i]; out.push_back(b?static_cast<uint8_t>(b-delta):0);} return out;
}

int classify_payload(const std::vector<uint8_t>& data) {
    if (data.size()!=MPC_FILE_SIZE) return 0;
    if (valid_tag(decode_nonzero(data,6,7,0x34))) return 2;
    if (valid_tag(decode_nonzero(data,0,7,0x2C))) return 1;
    return 0;
}

std::string type_name(int t) { return t==1?"MPCX (SiTCP-XG)":t==2?"MPC (normal SiTCP)":t==-1?"ambiguous":"unknown"; }

std::vector<uint8_t> reconstruct_xg(const std::vector<uint8_t>& e) {
    std::vector<uint8_t> p(e.begin(),e.begin()+16); p.insert(p.end(),e.begin()+18,e.begin()+24); return p;
}
std::vector<uint8_t> reconstruct_normal(const std::vector<uint8_t>& e) {
    std::vector<uint8_t> p(e.begin()+0x12,e.begin()+0x18); p.insert(p.end(),e.begin()+0x40,e.begin()+0x50); return p;
}

int detect_target(RbcpClient& c,const std::vector<uint8_t>& e,std::string& why) {
    auto xg=reconstruct_xg(e), normal=reconstruct_normal(e);
    bool xok=classify_payload(xg)==1, nok=classify_payload(normal)==2;
    if (xok&&!nok){why="EEPROM payload";return 1;}
    if (nok&&!xok){why="EEPROM payload";return 2;}
    if (!xok&&!nok){why="EEPROM payload not classified";return 0;}
    try { (void)read_retry(c,XG_PROBE_ADDRESS,1); why="XG register probe: readable"; return 1; }
    catch(const RbcpBusError&){why="XG register probe: bus error";return 2;}
    catch(const RbcpTimeout&){why="XG register probe: timeout";return -1;}
}

std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream f(path,std::ios::binary); if(!f) throw std::runtime_error("cannot open file: "+path);
    return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)),{});
}

void set_write_enable(RbcpClient& c,bool enabled) {
    auto ack=c.write(EEPROM_WRITE_ENABLE,{static_cast<uint8_t>(enabled?0x00:0xFF)});
    if(ack.size()!=1) throw RbcpError("unexpected RBCP ACK length for EEPROM write-enable");
}

std::vector<uint8_t> program(RbcpClient& c,const std::vector<uint8_t>& payload,int type) {
    std::vector<uint8_t> image;
    if(type==1){image=read_exact(c,EEPROM_BASE,24); std::copy(payload.begin(),payload.begin()+16,image.begin()); std::copy(payload.begin()+16,payload.end(),image.begin()+18);}
    else {image=read_exact(c,EEPROM_BASE,0x50); std::copy(payload.begin(),payload.begin()+6,image.begin()+0x12); std::copy(payload.begin()+6,payload.end(),image.begin()+0x40);}
    set_write_enable(c,true);
    try { write_exact(c,EEPROM_BASE,image,16); }
    catch(...) { try{set_write_enable(c,false);}catch(...){} throw; }
    set_write_enable(c,false);
    auto actual=read_exact(c,EEPROM_BASE,image.size());
    if(actual!=image){size_t i=0;while(i<image.size()&&actual[i]==image[i])++i;std::ostringstream os;os<<"EEPROM read-back verification failed"; if(i<image.size()) os<<" at 0x"<<std::hex<<(EEPROM_BASE+i)<<": expected 0x"<<(unsigned)image[i]<<", got 0x"<<(unsigned)actual[i]; throw RbcpError(os.str());}
    return actual;
}

void usage(const char* argv0){std::cerr<<"Usage: "<<argv0<<" <ip> <file> [--port N] [--timeout SEC]\n";}
}

int main(int argc,char** argv){
    try{
        if(argc==2 && (std::string(argv[1])=="-h" || std::string(argv[1])=="--help")){usage(argv[0]);return 0;}
        if(argc<3){usage(argv[0]);return 2;}
        std::string ip=argv[1], file_path=argv[2]; uint16_t port=DEFAULT_PORT; double timeout=DEFAULT_TIMEOUT;
        for(int i=3;i<argc;++i){std::string a=argv[i]; if(a=="--port"&&i+1<argc) port=static_cast<uint16_t>(std::stoul(argv[++i])); else if(a=="--timeout"&&i+1<argc) timeout=std::stod(argv[++i]); else if(a=="-h"||a=="--help"){usage(argv[0]);return 0;} else {throw std::runtime_error("unknown option: "+a);}}
        auto payload=read_file(file_path); int file_type=classify_payload(payload);
        if(payload.size()!=22||!(file_type==1||file_type==2)){std::cerr<<"ERROR: invalid/unknown 22-byte MPC payload (writer type "<<file_type<<")\n";return 2;}
        RbcpClient client(ip,port,timeout); auto eeprom=read_exact(client,EEPROM_BASE,EEPROM_READ_SIZE); std::string detection; int target_type=detect_target(client,eeprom,detection);
        field("command","write"); field("target",ip+":"+std::to_string(port)); field("file",file_path); field("file type",type_name(file_type)); field("target type",type_name(target_type)); field("detection",detection); field("writer type",std::to_string(file_type)); field("file payload",hex_bytes(payload));
        if((target_type==1||target_type==2)&&target_type!=file_type){field("status","REFUSED: TARGET TYPE MISMATCH");return 7;}
        if(!(target_type==1||target_type==2)){field("status","REFUSED: TARGET TYPE NOT DETECTED");return 7;}
        field("operation","programming EEPROM"); auto rb=program(client,payload,file_type);
        if(file_type==1){field("preserved FC10..FC11",hex_bytes(rb,16,18));field("read-back FC00..FC17",hex_bytes(rb));field("read-back MAC",hex_bytes(rb,18,24,':'));}
        else {field("read-back MAC",hex_bytes(rb,0x12,0x18,':'));field("read-back FC40..FC4F",hex_bytes(rb,0x40,0x50));}
        field("write","OK");field("read-back verify","OK");field("EEPROM write protect","ENABLED");field("status","WRITE OK"); return 0;
    } catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}
}
