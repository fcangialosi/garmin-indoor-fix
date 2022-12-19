import sys
import dateutil.parser
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
# Convert XML tag to proper namespace for TCX file
def GTag(tag):
    return f"{{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}}{tag}"
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


"""
Adjust distances in TCX file based on laps text file
"""
def fix(tcx, laps):
    # Load target TCX file
    tree = ET.parse(tcx)
    root = tree.getroot()
    ET.register_namespace("","http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2")

    # Load txt file specifying *correct* lap distances (in miles)
    # Convert to meters since that's what TCX uses
    with open(laps) as f:
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
    assert len(laps) == len(laps_dist_miles), f"Found {len(laps)} in TCX, but {len(laps_dist_miles)} in laps text file"

    total_meters = 0.0
    total_time = 0.0
    prev_lap_end = None
    time_adjust = None
    for lap_idx in range(len(laps)):
        ### correct summary stats

        lap = laps[lap_idx]
        lap_dist = lap.find(GTag('DistanceMeters'))
        old_lap_meters = float(lap_dist.text)
        lap_dist_meters = laps_dist_meters[lap_idx]
        lap_dist.text = str(round(lap_dist_meters,2))

        if prev_lap_end:
            old_lap_start = dateutil.parser.parse(lap.attrib['StartTime'])
            lap.attrib['StartTime'] = tcx_date_str(prev_lap_end)
            time_adjust = old_lap_start - prev_lap_end

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
        lap_end_t = dateutil.parser.parse(tps[-1].find(GTag("Time")).text)
        adj_len = (lap_end_t - lap_start_t).total_seconds()
        recorded_len = float(lap.find(GTag('TotalTimeSeconds')).text)
        # if we're still off, the last point might have added some extra distance, so lets remove it just in case
        if abs(adj_len - recorded_len) > 2:
            track.remove(tps[-1])
            removed += 1
            tps = tps[:-1]
            lap_end_t = dateutil.parser.parse(tps[-1].find(GTag("Time")).text)
            adj_len = (lap_end_t - lap_start_t).total_seconds()
        # assert abs(adj_len - recorded_len) < 2, f"adj_len={adj_len}, rec_len={recorded_len}"

        lap_dist_miles = meters_to_miles(lap_dist_meters)
        print(f"lap {lap_idx+1}\t::\t{old_lap_meters/1000:.3f}m -> {float(lap_dist.text)/1000:.3f}km (total={total_meters/1000:.3f}km)\tdist={lap_dist_miles:.3f}\ttime={adj_len}\tsplit={mile_split(lap_dist_miles,adj_len)}")
        total_time += adj_len
        # print(f"\t\t... removed {removed} trackpoints")

        # scale datapoints 
        old_lap_start_dist = float(tps[0].find(GTag("DistanceMeters")).text)
        old_lap_dist = float(old_lap_end_dist) - old_lap_start_dist
        for tp in tps:
            tp_dist = tp.find(GTag("DistanceMeters"))
            old_tp_meters = float(tp_dist.text)
            frac = (old_tp_meters-old_lap_start_dist) / old_lap_dist
            new_tp_dist = frac * (lap_dist_meters) + total_meters
            # print(f"b={total_meters}, old={old_tp_meters}, frac={frac}, add={frac*lap_dist_meters} new={new_tp_dist}")
            tp_dist.text = str(new_tp_dist)
            remove_pause(tp, time_adjust)
        
        total_meters += lap_dist_meters
        prev_lap_end = dateutil.parser.parse(tp.find(GTag("Time")).text)

    # Write updated TCX
    out_tcx = tcx.split(".tcx")[0] + "-fixed.tcx"
    tree.write(out_tcx, xml_declaration=True)
    
    print(f"-> Total\tkm={total_meters/1000:.3f}\tmiles={meters_to_miles(total_meters):.3f}\tsplit={mile_split(meters_to_miles(total_meters), total_time)}")

if __name__ == '__main__':
    fire.Fire(fix)
