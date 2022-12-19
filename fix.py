import sys
import dateutil.parser
import xml.etree.ElementTree as ET

import fire

# Convert miles -> km -> meters
def miles_to_meters(miles):
    return miles * 1.60934 * 1000

def meters_to_miles(meters):
    return meters / 1000.0 / 1.60934

# Convert XML tag to proper namespace for TCX file
def GTag(tag):
    return f"{{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}}{tag}"

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
    prev_lap_end = None
    for lap_idx in range(len(laps)):
        ### correct summary stats

        lap = laps[lap_idx]
        lap_dist = lap.find(GTag('DistanceMeters'))
        old_lap_meters = float(lap_dist.text)
        lap_dist_meters = laps_dist_meters[lap_idx]
        lap_dist.text = str(round(lap_dist_meters,2))

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
        # tps = tps[:true_end_index+1]
        removed = 0
        for tp in tps[true_end_index+1:]:
            track.remove(tp)
            removed += 1

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
        # print(f"\t\t... removed {removed} trackpoints")

        print(f"lap {lap_idx+1}\t::\t{old_lap_meters/1000:.3f}m -> {float(lap_dist.text)/1000:.3f}km (total={total_meters/1000:.3f}km) adj_len={adj_len} rec_len={recorded_len}")

        # scale datapoints 
        old_lap_start_dist = float(tps[0].find(GTag("DistanceMeters")).text)
        old_lap_dist = float(old_lap_end_dist) - old_lap_start_dist
        for tp in tps:
            tp_dist = tp.find(GTag("DistanceMeters"))
            old_tp_meters = float(tp_dist.text)
            frac = (old_tp_meters-old_lap_start_dist) / old_lap_dist
            new_tp_dist = frac * (lap_dist_meters) + total_meters
            print(f"b={total_meters}, old={old_tp_meters}, frac={frac}, add={frac*lap_dist_meters} new={new_tp_dist}")
            tp_dist.text = str(new_tp_dist)
        
        total_meters += lap_dist_meters
        prev_lap_end = dateutil.parser.parse(tp.find(GTag("Time")))

    # Write updated TCX
    out_tcx = tcx.split(".tcx")[0] + "-fixed.tcx"
    tree.write(out_tcx, xml_declaration=True)
    
    print(f"Total km={total_meters/1000:.3f} miles={meters_to_miles(total_meters):.3f}")

if __name__ == '__main__':
    fire.Fire(fix)
