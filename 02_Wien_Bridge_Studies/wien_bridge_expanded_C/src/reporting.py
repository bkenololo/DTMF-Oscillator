"""Representative trace capture and timestep checks retained from the original workflow."""
import numpy as np


def inspect_representative(row, cfg, results, executable):
    from wien import read_raw, run_case, write_csv
    # Separate paths prevent diagnostic reruns from replacing the sweep evidence.
    folder = results/"representatives"/f"{row['target_hz']}Hz"
    measurement = run_case(row, cfg, executable, folder, force=True, keep_raw=True)
    if measurement["simulation_status"] != "ok":
        return dict(simulation_status="simulation_failed", error=measurement.get("error"))
    case_folder = folder/"cases"/row["case_id"]
    t, v = read_raw(case_folder/"waveform.raw")
    np.savez_compressed(folder/"trace.npz", time_s=t, output_v=v)
    # A compact, portable CSV for import into other plotting programs.
    selection = np.unique(np.r_[np.arange(0, len(t), 20), np.flatnonzero(t >= cfg["transient_stop_s"]-0.015)])
    np.savetxt(folder/"trace_excerpt.csv", np.column_stack((t[selection], v[selection])),
               delimiter=",", header="time_s,output_v", comments="")
    (case_folder/"waveform.raw").unlink()
    refined_cfg = dict(cfg, maximum_time_step_s=cfg["maximum_time_step_s"]/2)
    refined = run_case(row, refined_cfg, executable, folder/"half_timestep", force=True)
    check = dict(target_hz=row["target_hz"], R1_ohm=row["R1_ohm"], R2_ohm=row["R2_ohm"],
        original_maximum_timestep_s=cfg["maximum_time_step_s"],
        refined_maximum_timestep_s=refined_cfg["maximum_time_step_s"],
        original_frequency_hz=measurement.get("simulated_frequency_hz"),
        refined_frequency_hz=refined.get("simulated_frequency_hz"),
        original_vpp_v=measurement.get("steady_state_vpp_v"),
        refined_vpp_v=refined.get("steady_state_vpp_v"),
        original_thd_percent=measurement.get("thd_2_to_10_percent"),
        refined_thd_percent=refined.get("thd_2_to_10_percent"),
        original_status=measurement.get("oscillation_status"),
        refined_status=refined.get("oscillation_status"),
        simulation_status=refined.get("simulation_status"))
    if refined.get("simulated_frequency_hz") and measurement.get("simulated_frequency_hz"):
        check["frequency_change_percent"] = 100*abs(refined["simulated_frequency_hz"]-measurement["simulated_frequency_hz"])/refined["simulated_frequency_hz"]
    return check
