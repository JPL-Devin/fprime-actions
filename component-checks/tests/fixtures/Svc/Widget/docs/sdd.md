# Svc::Widget Component

## 1. Introduction

The `Svc::Widget` demonstrates the checklist checks.

## 2. Requirements

Requirement | Description | Parent | Verification Method
----------- | ----------- | ------ | -------------------
WID-001 | The `Svc::Widget` component shall START and STOP processing on command | SYS-010 | Unit Test
WID-002 | The `Svc::Widget` component shall report the WidgetCount telemetry channel | SYS-011 | Unit Test
WID-003 | The `Svc::Widget` component shall emit WidgetStarted and WidgetError events | SYS-011 | Unit Test
WID-004 | The `Svc::Widget` component shall use the THRESHOLD parameter | SYS-012 | Analysis
WID-005 | The `Svc::Widget` component shall produce WidgetRecord into WidgetContainer and OrphanContainer via productSendOut and productRequestOut | SYS-013 | Unit Test
WID-006 | The `Svc::Widget` component shall accept data on dataIn, run on the run port, and forward via dataOut, cmdIn, cmdRegOut, cmdResponseOut, eventOut, tlmOut, timeGetOut, prmGetOut, prmSetOut, productRecvIn | SYS-014 | Inspection
WID-007 | The `Svc::Widget` component shall allow SET_PRIORITY to change data product priority | | Unit Test

## 3. Design

The design covers WID-001, WID-002, WID-003, WID-004, WID-005, and WID-006.
