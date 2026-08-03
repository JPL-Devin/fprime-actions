#include "Svc/Widget/Widget.hpp"
#include "Fw/Types/Assert.hpp"
#include "Fw/Buffer/Buffer.hpp"
#include "Os/Mutex.hpp"

namespace Svc {

void Widget::run_handler(FwIndexType portNum, U32 context) {}

void Widget::dataIn_handler(FwIndexType portNum, Fw::Buffer& buffer) {}

void Widget::START_cmdHandler(FwOpcodeType opCode, U32 cmdSeq) {}

void Widget::STOP_cmdHandler(FwOpcodeType opCode, U32 cmdSeq) {}

void Widget::SET_PRIORITY_cmdHandler(FwOpcodeType opCode, U32 cmdSeq, U32 priority) {}

void Widget::action_doStart(SmId smId, DeviceSm::Signal signal) {}

}  // namespace Svc
