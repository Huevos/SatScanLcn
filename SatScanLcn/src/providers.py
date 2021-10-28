# for localized messages
from . import _
from enigma import eDVBFrontendParametersSatellite

PROVIDERS = {
	"Orange_TV_16E": {
		"name": _("Orange TV"),
		"transponder": {
			"frequency": 11324000,
			"symbol_rate": 30000000,
			"polarization": eDVBFrontendParametersSatellite.Polarisation_Vertical,
			"fec_inner": eDVBFrontendParametersSatellite.FEC_2_3,
			"orbital_position": 160,
			"system": eDVBFrontendParametersSatellite.System_DVB_S2,
			"modulation": eDVBFrontendParametersSatellite.Modulation_8PSK,
			"roll_off": eDVBFrontendParametersSatellite.RollOff_alpha_0_20,
			"original_network_id": 0x016e,
			"transport_stream_id": 0x9e98,
		},
	},
	"Canal_Digitaal_HD": {
		"name": _("Canal Digitaal HD"), 
		"transponder": {
			"frequency": 12515000,
			"symbol_rate": 22000000,
			"polarization": eDVBFrontendParametersSatellite.Polarisation_Horizontal,
			"fec_inner": eDVBFrontendParametersSatellite.FEC_5_6,
			"orbital_position": 192,
			"system": eDVBFrontendParametersSatellite.System_DVB_S,
			"modulation": eDVBFrontendParametersSatellite.Modulation_QPSK,
			"roll_off": eDVBFrontendParametersSatellite.RollOff_alpha_0_35,
			"original_network_id": 0x0035,
			"transport_stream_id": 0x0451,
		},
		"nit": {
			"nit_pid": 0x385,
			"nit_current_table_id": 0xbc,
			"nit_other_table_id": 0x00,
		},
	},
}