#include <cstdlib>
#include <map>
#include <sstream>
#include <string>
#include <iostream>
#include <fstream>
#include <vector>
namespace android::base {
std::string Trim(const std::string& text) {
    auto first=text.find_first_not_of(" \t\r\n");
    if (first==std::string::npos) return {};
    auto last=text.find_last_not_of(" \t\r\n");
    return text.substr(first,last-first+1);
}
}
bool containsNumber(const std::string& values, long expected) {
    std::istringstream stream(values);
    std::string token;
    while (stream >> token) {
        char* end = nullptr;
        const long number = std::strtol(token.c_str(), &end, 10);
        if (end != token.c_str() && *end == '\0' && number == expected) return true;
    }
    return false;
}

bool eldConnectionValid(const std::string& eld) {
    std::istringstream lines(eld);
    std::string line;
    while (std::getline(lines, line)) {
        std::istringstream tokens(line);
        std::string key, value;
        if (tokens >> key >> value &&
            (key == "monitor_present" || key == "eld_valid") && value != "1") return false;
    }
    // hdmi-codec's actual ELD format omits these two fields entirely.
    return true;
}

// Kernel ELD describes the connected sink, not merely an HDMI connector.
// Require one LPCM SAD covering the only advertised profile: 48 kHz, 16-bit stereo.
bool eldSupportsPcm(const std::string& eld) {
    std::map<std::string, std::string> fields;
    std::istringstream lines(eld);
    std::string line;
    while (std::getline(lines, line)) {
        std::istringstream tokens(line);
        std::string key, value;
        if (tokens >> key) {
            std::getline(tokens, value);
            fields[key] = ::android::base::Trim(value);
        }
    }
    if (!eldConnectionValid(eld)) return false;
    const int count = std::atoi(fields["sad_count"].c_str());
    if (count < 1 || count > 15) return false;
    for (int sad = 0; sad < count; ++sad) {
        const std::string prefix = "sad" + std::to_string(sad) + "_";
        if (fields[prefix + "coding_type"].find("LPCM") == std::string::npos) continue;
        if (std::atoi(fields[prefix + "channels"].c_str()) < 2) continue;
        if (containsNumber(fields[prefix + "rates"], 48000) &&
            containsNumber(fields[prefix + "bits"], 16)) return true;
    }
    return false;
}

// A valid CTA Basic Audio flag guarantees LPCM stereo at 32/44.1/48 kHz,
// 16-bit. Otherwise require all three capabilities in the same LPCM SAD.
bool edidSupportsPcm(const std::string& bytes) {
    static const unsigned char header[] = {0,255,255,255,255,255,255,0};
    if (bytes.size() < 128) return false;
    const auto byte = [&](size_t offset) { return static_cast<unsigned char>(bytes[offset]); };
    for (size_t i = 0; i < sizeof(header); ++i) if (byte(i) != header[i]) return false;
    const size_t blocks = 1 + byte(126);
    if (bytes.size() != blocks * 128) return false;
    for (size_t block = 0; block < blocks; ++block) {
        unsigned sum = 0;
        for (size_t i = 0; i < 128; ++i) sum += byte(block * 128 + i);
        if ((sum & 255) != 0) return false;
    }
    bool supported = false;
    for (size_t block = 1; block < blocks; ++block) {
        const size_t base = block * 128;
        if (byte(base) != 0x02 || byte(base + 1) < 3) continue;
        const size_t end = byte(base + 2);
        if (end != 0 && (end < 4 || end > 127)) return false;
        supported |= (byte(base + 3) & 0x40) != 0;
        for (size_t pos = 4; end != 0 && pos < end;) {
            const unsigned tag = byte(base + pos) >> 5;
            const size_t count = byte(base + pos) & 31;
            ++pos;
            if (pos + count > end) return false;
            if (tag == 1) {
                if (count % 3 != 0) return false;
                for (size_t sad = pos; sad + 2 < pos + count; sad += 3) {
                    const unsigned info = byte(base + sad);
                    if (((info >> 3) & 15) == 1 && (info & 7) + 1 >= 2 &&
                        (byte(base + sad + 1) & 4) && (byte(base + sad + 2) & 1)) {
                        supported = true;
                    }
                }
            }
            pos += count;
        }
    }
    return supported;
}


int main(int argc, char** argv) {
 const std::string header="monitor_present 1\neld_valid 1\nsad_count 1\n";
 const std::string good="sad0_coding_type [0x1] LPCM\nsad0_channels 2\nsad0_rates [0xe0] 32000 44100 48000\nsad0_bits [0xe0000] 16 20 24\n";
 std::vector<std::pair<std::string,bool>> tests={
  {header+good,true},
  {"sad_count 1\n"+good,true},
  {"monitor_present 1\neld_valid 1\nsad_count 0\n",false},
  {"monitor_present 0\neld_valid 1\nsad_count 1\n"+good,false},
  {"monitor_present 1\neld_valid 0\nsad_count 1\n"+good,false},
  {"",false},
  {header+"sad0_coding_type [0x2] AC-3\nsad0_channels 6\nsad0_rates 48000\nsad0_bits 16\n",false},
  {header+"sad0_coding_type LPCM\nsad0_channels 1\nsad0_rates 48000\nsad0_bits 16\n",false},
  {header+"sad0_coding_type LPCM\nsad0_channels 2\nsad0_rates 44100\nsad0_bits 16\n",false},
  {header+"sad0_coding_type LPCM\nsad0_channels 2\nsad0_rates 480000\nsad0_bits 16\n",false},
  {header+"sad0_coding_type LPCM\nsad0_channels 2\nsad0_rates 48000\nsad0_bits 160\n",false},
  {header+"sad0_coding_type LPCM\nsad0_channels 8\nsad0_rates 48000\nsad0_bits 24\n",false},
  {"monitor_present 1\neld_valid 1\nsad_count 2\nsad0_coding_type LPCM\nsad0_channels 2\nsad0_rates 44100\nsad0_bits 16\nsad1_coding_type AC-3\nsad1_channels 6\nsad1_rates 48000\nsad1_bits 16\n",false},
  {"monitor_present 1\neld_valid 1\nsad_count 2\nsad0_coding_type AC-3\nsad0_channels 6\nsad0_rates 48000\nsad0_bits 16\nsad1_coding_type [0x1] LPCM\nsad1_channels 8\nsad1_rates 32000 44100 48000\nsad1_bits 16 24\n",true},
 };
 for (size_t i=0;i<tests.size();++i) {
  if (eldSupportsPcm(tests[i].first)!=tests[i].second) { std::cerr<<"failed "<<i<<"\n";return 1; }
 }
 std::cout<<"ELD boundary cases passed: "<<tests.size()<<"\n";
 const auto checksum=[](std::string& data) {
  for (size_t base=0;base<data.size();base+=128) {
   unsigned sum=0;for(size_t i=0;i<127;++i)sum+=static_cast<unsigned char>(data[base+i]);
   data[base+127]=static_cast<char>((256-(sum&255))&255);
  }
 };
 std::string basic(256,0);for(size_t i=1;i<7;++i)basic[i]=static_cast<char>(255);
 basic[126]=1;basic[128]=2;basic[129]=3;basic[131]=0x40;checksum(basic);
 if(!edidSupportsPcm(basic))return 2;
 std::string bad=basic;bad[20]=1;if(edidSupportsPcm(bad))return 3;
 std::string old=basic;old[129]=2;checksum(old);if(edidSupportsPcm(old))return 10;
 std::string extra=basic+std::string(128,0);if(edidSupportsPcm(extra))return 11;
 std::string noAudio=basic;noAudio[131]=0;checksum(noAudio);if(edidSupportsPcm(noAudio))return 4;
 std::string sad=noAudio;sad[130]=8;sad[132]=0x23;sad[133]=0x09;sad[134]=0x04;sad[135]=0x01;checksum(sad);
 if(!edidSupportsPcm(sad))return 5;
 std::string compressed=sad;compressed[133]=0x11;checksum(compressed);if(edidSupportsPcm(compressed))return 6;
 std::string split=sad;split[130]=11;split[132]=0x26;split[134]=0x02;split[136]=0x11;split[137]=0x04;split[138]=0x01;checksum(split);
 if(edidSupportsPcm(split))return 7;
 if(argc==1) {
  std::cout<<"EDID capability cases passed: 8 (synthetic fixtures only)\n";
  return 0;
 }
 if(argc!=2)return 8;
 std::ifstream in(argv[1],std::ios::binary);std::string actual((std::istreambuf_iterator<char>(in)),{});
 if(actual.empty()||edidSupportsPcm(actual))return 9;
 std::cout<<"EDID capability cases passed: 9 (including actual no-audio monitor)\n";
}
