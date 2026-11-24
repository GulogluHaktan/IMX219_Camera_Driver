/* Minimal conftest for building nv_imx219 alone against the L4T R39.2.1 kernel 6.8.12 (Update 167). Values = what NVIDIA's conftest yields here.
 * NV_TEGRA_PMC_IO_PAD_POWER_ENABLE_PRESENT IS defined: NVIDIA's 6.8 kernel has tegra_pmc_io_pad_power_enable() (include/soc/tegra/pmc.h), and the
 * macro adds `struct tegra_pmc *pmc` to struct camera_common_data. Leaving it undefined shifted every later field by 8 bytes (priv at 584 vs 592):
 * the module loaded but every capture failed (VI discarded all frames). */
#ifndef __NV_CONFTEST_STUB_H__
#define __NV_CONFTEST_STUB_H__
#define NV_I2C_DRIVER_STRUCT_PROBE_WITHOUT_I2C_DEVICE_ID_ARG 1   /* Linux >= 6.3 */
#define NV_TEGRA_PMC_IO_PAD_POWER_ENABLE_PRESENT 1               /* backported into NVIDIA's 6.8 kernel */
/* NV_I2C_DRIVER_STRUCT_REMOVE_RETURN_TYPE_INT: not defined (void remove since 6.1) */
#endif
