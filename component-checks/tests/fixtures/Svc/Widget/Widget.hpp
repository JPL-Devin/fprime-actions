#ifndef Svc_Widget_HPP
#define Svc_Widget_HPP

#include "Svc/Widget/WidgetComponentAc.hpp"

namespace Svc {

class Widget final : public WidgetComponentBase {
  public:
    explicit Widget(const char* compName);
};

}  // namespace Svc

#endif
