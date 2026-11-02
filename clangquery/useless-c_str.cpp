#include "../../Unvanquished/daemon/src/common/Common.h"

void UselessCStr()
{
    std::string str;
    Str::StringRef sref("a");

    void f1(const std::string &);
    f1(sref.c_str()); //!

    void f2(Str::StringRef);
    f2(str.c_str()); //!

    std::string s(std::string().c_str()); //!

    Log::Notice(str.c_str()); //!

    Str::Format("%s", str.c_str()); //!
    
    Sys::Drop("%s", Str::StringRef("").c_str()); //!

    Log::Logger l5("");
    l5.Warn(str.c_str()); //!
    
    Log::Logger l6(sref.c_str()); //!

    // NON EXAMPLES
    void f7(const char*);
    f7(str.c_str());
}
