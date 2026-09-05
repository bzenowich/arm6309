/* STM32G431CBU6 — 128K flash, 22K SRAM (SRAM1 16K + SRAM2 6K), 10K CCM SRAM.
 *
 * Package is UFQFPN48 (42 GPIO); the die and therefore this memory map are the
 * same on the LQFP48 the plan used to specify. See cpu/docs/plan.md §3.2.
 *
 * CCM SRAM is zero-wait and sits on the I-bus, so the bus loop lives there.
 * Flash is 4 wait states at 170 MHz — far too slow for the hot path.
 *
 * CCM is also aliased at 0x20005800 (contiguous after SRAM1+SRAM2); we use the
 * 0x10000000 window because that is the one reachable over the I-bus. Note the
 * corollary: DMA reaches CCM ONLY through the alias (RM0440 §2.4), so nothing a
 * DMA channel must read may be placed in this region by the __ccm* attributes.
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = 128K
    RAM    (rwx) : ORIGIN = 0x20000000, LENGTH = 22K
    CCMRAM (rwx) : ORIGIN = 0x10000000, LENGTH = 10K
}

_stack_top  = ORIGIN(RAM) + LENGTH(RAM);
_stack_size = 2K;

SECTIONS
{
    .isr_vector : ALIGN(512) {
        KEEP(*(.isr_vector))
    } > FLASH

    .text : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.glue_7 .glue_7t)
        KEEP(*(.init))
        KEEP(*(.fini))
        . = ALIGN(4);
    } > FLASH

    .ARM.exidx : {
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    } > FLASH

    /* Initialised data: loaded from flash into SRAM at reset. */
    _sidata = LOADADDR(.data);
    .data : ALIGN(4) {
        _sdata = .;
        *(.data .data.*)
        . = ALIGN(4);
        _edata = .;
    } > RAM AT > FLASH

    .bss (NOLOAD) : ALIGN(4) {
        _sbss = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /* Hot path. Code and data marked __ccm / __hot land here and are copied
     * out of flash at reset, exactly like .data. */
    _siccm = LOADADDR(.ccmram);
    .ccmram : ALIGN(4) {
        _sccm = .;
        *(.ccmram.text .ccmram.text.*)
        *(.ccmram.data .ccmram.data.*)
        . = ALIGN(4);
        _eccm = .;
    } > CCMRAM AT > FLASH

    .ccmram_bss (NOLOAD) : ALIGN(4) {
        _sccmbss = .;
        *(.ccmram.bss .ccmram.bss.*)
        . = ALIGN(4);
        _eccmbss = .;
    } > CCMRAM

    /* Fail the link rather than silently overflowing the stack. */
    .stack_guard (NOLOAD) : {
        . = ALIGN(8);
        . = . + _stack_size;
    } > RAM

    /DISCARD/ : { *(.ARM.attributes) }
}
