module Svc {

  @ A widget state machine
  state machine DeviceSm {
    initial enter IDLE
    action doStart
    action doStop
    state IDLE {
      on Start do { doStart } enter RUNNING
    }
    state RUNNING {
      on Stop do { doStop } enter IDLE
    }
  }

  @ An example widget component
  active component Widget {

    # ----- special ports (no handlers required) -----
    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
    event port eventOut
    telemetry port tlmOut
    time get port timeGetOut
    param get port prmGetOut
    param set port prmSetOut
    product request port productRequestOut
    product recv port productRecvIn
    product send port productSendOut

    # ----- typed ports -----
    @ Rate group input
    async input port run: Svc.Sched

    @ Data input
    # Deliberately sync (not the recommended all-async profile for an
    # active component): exercises the parser's sync-input-port coverage.
    sync input port dataIn: Fw.BufferSend

    @ Data output
    output port dataOut: Fw.BufferSend

    # ----- commands -----
    @ Start the widget
    async command START()

    @ Stop the widget
    async command STOP()

    @ Set data product priority
    async command SET_PRIORITY(priority: U32)

    # ----- telemetry -----
    @ Number of widgets processed
    telemetry WidgetCount: U32

    # ----- events -----
    @ Widget started
    event WidgetStarted() severity activity high format "Widget started"

    @ Widget error
    event WidgetError(code: U32) severity warning high format "Widget error {}"

    # ----- parameters -----
    @ Processing threshold
    param THRESHOLD: U32 default 10

    # ----- data products -----
    @ Widget record
    product record WidgetRecord: U32

    @ Widget container
    product container WidgetContainer id 0x01 default priority 10

    @ Container missing default priority
    product container OrphanContainer id 0x02

    # ----- state machine instance -----
    state machine instance deviceSm: DeviceSm

  }

}
