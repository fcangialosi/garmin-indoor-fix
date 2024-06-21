import sys
import dateutil.parser
import datetime
import xml.etree.ElementTree as ET

import fire

"""
Helper Functions
"""
# Convert miles -> km -> meters
def miles_to_meters(miles):
    return miles * 1.60934 * 1000
# Convert meters -> km -> miles
def meters_to_miles(meters):
    return meters / 1000.0 / 1.60934
# Datetime format string expected by TCX
def tcx_date_str(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
def dt_add_seconds(dt, secs):
    return (dt + datetime.timedelta(0, secs))
# Convert XML tag to proper namespace for TCX file
def GTag(tag):
    return f"{{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}}{tag}"
def set_tp_time_by_offset(tp, lap_start, adjust):
    time_tag = tp.find(GTag("Time"))
    new_t = dt_add_seconds(lap_start, adjust)
    time_tag.text = tcx_date_str(new_t)
# Offset trackpoint time by "adjust"
def remove_pause(tp, adjust):
    if adjust:
        time_tag = tp.find(GTag("Time"))
        t = dateutil.parser.parse(time_tag.text)
        new_t = t - adjust
        time_tag.text = tcx_date_str(new_t)
def mile_split(dist, seconds):
    pace = (seconds / 60.0) / dist
    pace_min = int(pace)
    pace_sec = int((pace % 1) * 60)
    return f"{pace_min}:{pace_sec:02d}/mi"

# returns pace as seconds per mile (rather than the typical minutes per mile)
def parse_pace_secs_per_mile(s):
    m,s = s.split(":")
    return float(m) * 60 + float(s)

# In normal mode, the expectation is that there are no pause within a lap, only pause *between* laps
# In midlap pause (more common on treadmill), the expectation is that there are pauses within a lap
# Expects laps file to specify distances in miles by default, but with --set-pace uses paces instead (for treadmill)
"""
Adjust distances in TCX file based on laps text file
"""
def fix(tcx, laps, use_recorded_time = False, midlap_pause = False, set_pace = False):
    # Load target TCX file
    tree = ET.parse(tcx)
    root = tree.getroot()
    ET.register_namespace("","http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2")

    # Load txt file specifying *correct* lap distances (in miles)
    # Convert to meters since that's what TCX uses
    with open(laps) as f:
        if set_pace:
            laps_paces = [parse_pace_secs_per_mile(l.strip()) for l in f.readlines()]
        else:
            laps_dist_miles = [float(l.strip()) for l in f.readlines()]
            laps_dist_meters = [miles_to_meters(x) for x in laps_dist_miles]

    # Extract the activity tag
    acts = root.find(GTag("Activities"))
    acts_list = acts.findall(GTag("Activity"))
    # Should only be one activity here!
    assert len(acts_list) == 1
    act = acts_list[0]
    laps = act.findall(GTag('Lap'))
    # Number of laps must match what the text file specifies
    if set_pace:
        assert len(laps) == len(laps_paces), f"Found {len(laps)} in TCX, but {len(laps_paces)} in laps paces text file"
    else:
        assert len(laps) == len(laps_dist_miles), f"Found {len(laps)} in TCX, but {len(laps_dist_miles)} in laps distance text file"

    total_meters = 0.0
    total_time = 0.0
    orig_total_time = 0.0
    prev_lap_start_t = None
    prev_lap_end = None
    time_adjust = None
    for lap_idx in range(len(laps)):
        ### correct summary stats

        lap = laps[lap_idx]
        lap_dist = lap.find(GTag('DistanceMeters'))
        recorded_len = float(lap.find(GTag('TotalTimeSeconds')).text)
        old_lap_meters = float(lap_dist.text)

        if set_pace:
            lap_pace = laps_paces[lap_idx]
            lap_dist_miles = recorded_len / lap_pace
            lap_dist_meters = miles_to_meters(lap_dist_miles)
        else:
            lap_dist_meters = laps_dist_meters[lap_idx]
        lap_dist.text = str(round(lap_dist_meters,2))

        old_lap_start = dateutil.parser.parse(lap.attrib['StartTime'])
        if prev_lap_end:
            # lap.attrib['StartTime'] = tcx_date_str(prev_lap_end)
            lap.set('StartTime', tcx_date_str(prev_lap_end))
            time_adjust = old_lap_start - prev_lap_end
        else:
            prev_lap_end = old_lap_start

        ### correct individual datapoints
        track = lap.find(GTag("Track"))
        tps = track.findall(GTag("Trackpoint"))

        # remove extraneous trackpoints at the end
        old_lap_end_dist = tps[-1].find(GTag("DistanceMeters")).text
        true_end_index = None
        for i in range(len(tps)-1, 0, -1):
            dist = tps[i].find(GTag("DistanceMeters")).text
            if dist != old_lap_end_dist:
                true_end_index = i+1
                break
        removed = 0
        for tp in tps[true_end_index+1:]:
            track.remove(tp)
            removed += 1
        tps = tps[:true_end_index+1]

        # ensure we still have the true end distance point
        assert tps[-1].find(GTag("DistanceMeters")).text == old_lap_end_dist

        # ensure our trimmed data is close enough to the total recorded in the summary of the lap
        lap_start_t = dateutil.parser.parse(tps[0].find(GTag("Time")).text)
        if prev_lap_start_t:
            orig_total_time += (lap_start_t - prev_lap_start_t).total_seconds()
        prev_lap_start_t = lap_start_t
        lap_end_t = dateutil.parser.parse(tps[-1].find(GTag("Time")).text)
        adj_len = (lap_end_t - lap_start_t).total_seconds()
        if use_recorded_time:
            adj_len = recorded_len
        else:
            # if we're still off, the last point might have added some extra distance, so lets remove it just in case
            if abs(adj_len - recorded_len) > 2:
                track.remove(tps[-1])
                removed += 1
                tps = tps[:-1]
                lap_end_t = dateutil.parser.parse(tps[-1].find(GTag("Time")).text)
                adj_len = (lap_end_t - lap_start_t).total_seconds()
            assert abs(adj_len - recorded_len) < 2, f"adj_len={adj_len}, rec_len={recorded_len}. if recorded looks good, add --use-recorded-time"

        lap_dist_miles = meters_to_miles(lap_dist_meters)
        print(f"lap {lap_idx+1}\t::\t{old_lap_meters/1000:.3f}m -> {float(lap_dist.text)/1000:.3f}km (total={total_meters/1000:.3f}km)\tdist={lap_dist_miles:.3f}\ttime={adj_len}\tsplit={mile_split(lap_dist_miles,adj_len)}")
        total_time += adj_len
        # print(f"\t\t... removed {removed} trackpoints")

        # scale datapoints
        old_lap_start_dist = float(tps[0].find(GTag("DistanceMeters")).text)
        old_lap_dist = float(old_lap_end_dist) - old_lap_start_dist
        for tp_idx, tp in enumerate(tps):
            tp_dist = tp.find(GTag("DistanceMeters"))
            old_tp_meters = float(tp_dist.text)
            frac = (old_tp_meters-old_lap_start_dist) / old_lap_dist
            new_tp_dist = frac * (lap_dist_meters) + total_meters
            # print(f"b={total_meters}, old={old_tp_meters}, frac={frac}, add={frac*lap_dist_meters} new={new_tp_dist}")
            tp_dist.text = str(new_tp_dist)
            if midlap_pause:
                set_tp_time_by_offset(tp, lap_start=prev_lap_end, adjust=tp_idx)
            else:
                remove_pause(tp, time_adjust)


        total_meters += lap_dist_meters
        if midlap_pause:
            prev_lap_end = dt_add_seconds(prev_lap_end, adj_len)
        else:
            prev_lap_end = dateutil.parser.parse(tp.find(GTag("Time")).text)

    orig_total_time += (lap_end_t - lap_start_t).total_seconds()
    # Write updated TCX
    out_tcx = tcx.split(".tcx")[0] + "-fixed.tcx"
    tree.write(out_tcx, xml_declaration=True)

    print(f"-> Total\tkm={total_meters/1000:.3f}\tmiles={meters_to_miles(total_meters):.3f}\tsplit={mile_split(meters_to_miles(total_meters), total_time)}")
    print(f"-> {orig_total_time} -> {total_time}")

if __name__ == '__main__':
    fire.Fire(fix)
