register_fprime_module(
  SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/Widget.cpp"
  AUTOCODER_INPUTS
    "${CMAKE_CURRENT_LIST_DIR}/Widget.fpp"
  DEPENDS
    Fw_Types
    Os
)

register_fprime_ut(
  SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/test/ut/WidgetTester.cpp"
  DEPENDS
    Fw_Types
    STest
)
