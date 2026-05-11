import os
import csv
import re
import math


RAW_COLUMNS = {
    0: 'raw_iA',
    1: 'raw_iR',
    2: 'raw_vA',
    3: 'raw_iB',
    4: 'raw_vB',
    5: 'raw_iWPT',
    6: 'raw_vWPT',
}

def solve_linear_regression(x_list, y_list):
    n = len(x_list)
    if n < 2:
        return 1.0, 0.0, 0.0 # Default
    
    sum_x = sum(x_list)
    sum_y = sum(y_list)
    sum_xy = sum(x * y for x, y in zip(x_list, y_list))
    sum_xx = sum(x * x for x in x_list)
    
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 1.0, 0.0, 0.0
        
    k = (n * sum_xy - sum_x * sum_y) / denominator
    b = (sum_y - k * sum_x) / n
    
    # Calculate R-squared
    mean_y = sum_y / n
    ss_tot = sum((y - mean_y) ** 2 for y in y_list)
    ss_res = sum((y - (k * x + b)) ** 2 for x, y in zip(x_list, y_list))
    
    if ss_tot == 0:
        r_squared = 1.0 if ss_res == 0 else 0.0
    else:
        r_squared = 1 - (ss_res / ss_tot)
    
    return k, b, r_squared

def parse_csv_value(filepath, index):
    # Supports:
    # 1) Ozone CSV: lines like 2,"[index]",value,
    # 2) capture_calibration.py CSV: header+rows with raw_* columns
    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        head = f.read(1024)
        f.seek(0)

        raw_col = RAW_COLUMNS.get(index)
        if raw_col and raw_col in head:
            reader = csv.DictReader(f)
            vals = []
            for row in reader:
                cell = row.get(raw_col, '').strip()
                if not cell:
                    continue
                vals.append(float(cell))
            if vals:
                return sum(vals) / len(vals)
            return None

        content = f.read()
        pattern = re.compile(r'^\s*2,"\[{}\]",([\d\.]+),'.format(index), re.MULTILINE)
        matches = pattern.findall(content)
        if matches:
            float_vals = [float(x) for x in matches]
            return sum(float_vals) / len(float_vals)
    return None

def main():
    calib_dir = r'd:\code\rm\supercap\supercap_25_claude\PowerControlBoard_Software_FieldVersion\debug\calibration'
    files = sorted(os.listdir(calib_dir))
    
    # Data stores: key = channel name, value = list of (raw, target) tuples
    data = {
        'vA': [],
        'vB': [],
        'iA': [],
        'iB': [],
        'iR': [],
        'vWPT': [],
        'iWPT': []
    }
    
    # Mapping from tempData index to channel
    index_map = {
        0: 'iA',
        1: 'iR',
        2: 'vA',
        3: 'iB',
        4: 'vB',
        5: 'iWPT',
        6: 'vWPT'
    }
    
    used_default_vin_for_power = False

    for filename in files:
        if not filename.lower().endswith('.csv'):
            continue
            
        filepath = os.path.join(calib_dir, filename)
        
        # Determine targets
        targets = {} # channel -> target_value
        
        # Parse filename
        # 1. AxxV or Axxv: No load, Voltage xx
        number = r'([+-]?\d+(?:\.\d+)?)'
        m_av = re.match(rf'A{number}V\.csv', filename, re.IGNORECASE)
        # 2. AxxA[@VinV]: Load on REF, Current xx, optional measured source voltage
        m_aa = re.match(rf'A{number}A(?:@({number})V)?\.csv', filename, re.IGNORECASE)
        # 3. BxxAyyV[@VinV]: Load on CAP, Current xx, CAP voltage yy, optional source voltage
        m_b = re.match(rf'B{number}A(\d+(?:\.\d+)?)V(?:@({number})V)?\.csv', filename, re.IGNORECASE)
        
        if m_av:
            vol = float(m_av.group(1))
            targets['vA'] = vol
            targets['iA'] = 0.0
            targets['iB'] = 0.0
            targets['iR'] = 0.0
            # vB?
            
        elif m_aa:
            curr = float(m_aa.group(1))
            vin_meas = float(m_aa.group(2)) if m_aa.group(2) else None
            if vin_meas is not None:
                targets['vA'] = vin_meas
            targets['iA'] = 0.0 # iA does not seem to measure REF current based on data
            targets['iR'] = curr # REF current positive (in)
            targets['iB'] = 0.0
            
        elif m_b:
            curr = float(m_b.group(1))
            vol = float(m_b.group(2))
            vin_meas = float(m_b.group(3)) if m_b.group(3) else None
            if vin_meas is not None:
                targets['vA'] = vin_meas
            targets['vB'] = vol
            targets['iB'] = curr # CAP current positive (out? wait)
            # In Bxx points, source-side current path contributes to iR too.
            # Using iR=0 causes systematic bias for iR calibration.
            
            # Estimate iA target
            # P_in = P_out / Efficiency
            # vA * iA = (vB * iB) / 0.9 (Assume 90% efficiency)
            # iA = (vB * iB) / (vA * 0.9)
            vin_for_power = vin_meas if vin_meas is not None else 24.0
            if vin_meas is None:
                used_default_vin_for_power = True
            if vin_for_power > 0:
                targets['iA'] = (vol * curr) / (vin_for_power * 0.9)
                targets['iR'] = targets['iA']
            
        else:
            print(f"Skipping {filename}: Unknown format")
            continue
            
        print(f"Processing {filename}...")
        
        # Extract raw values
        for idx, channel in index_map.items():
            raw_val = parse_csv_value(filepath, idx)
            if raw_val is not None:
                if channel in targets:
                    target_val = targets[channel]
                    data[channel].append((raw_val, target_val))
                    print(f"  {channel}: Raw={raw_val:.2f}, Target={target_val:.2f}")
    
    print("\nResults:")

    if used_default_vin_for_power:
        print("[WARN] Some BxxAyyV files did not provide source voltage. iA target estimate used default 24V.")
        print("       Recommended naming: B2A18.5V@23.7V.csv")
    
    # Alphas
    ADC_VSENSE_ALPHA = 0.8
    ADC_ISENSE_ALPHA = 0.9 # Need to verify this value
    
    results = {}
    
    for channel in ['vA', 'vB', 'iA', 'iB', 'iR']:
        pts = data[channel]
        if not pts:
            print(f"No data for {channel}")
            continue
            
        x_vals = [p[0] for p in pts]
        y_vals = [p[1] for p in pts]
        
        k_fit, b_fit, r_sq = solve_linear_regression(x_vals, y_vals)
        
        print(f"{channel}: K_fit={k_fit:.8f}, B_fit={b_fit:.8f}, R^2={r_sq:.6f}")
        
        k_code = k_fit
        b_code = b_fit
        
        if channel == 'iR':
            # iR = -(Raw*K + B)
            # Target = Raw*K_fit + B_fit
            # -(Raw*K + B) = Raw*K_fit + B_fit
            # Raw*(-K) + (-B) = Raw*K_fit + B_fit
            # K = -K_fit
            # B = -B_fit
            k_code = -k_fit
            b_code = -b_fit
            
        elif channel in ['vA', 'vB']:
            # B_code = B_fit * Alpha
            b_code = b_fit * ADC_VSENSE_ALPHA
            
        results[channel] = (k_code, b_code)
        
    print("\nGenerated Code:")
    if 'vA' in results:
        print(f"#define ADC_VA_K        {results['vA'][0]:.15f}f")
        print(f"#define ADC_VA_B        {results['vA'][1]:.9f}f")
    if 'vB' in results:
        print(f"#define ADC_VB_K        {results['vB'][0]:.15f}f")
        print(f"#define ADC_VB_B        {results['vB'][1]:.9f}f")
    if 'iA' in results:
        print(f"#define ADC_IA_K        {results['iA'][0]:.15f}f")
        print(f"#define ADC_IA_B        {results['iA'][1]:.9f}f")
    if 'iB' in results:
        print(f"#define ADC_IB_K        {results['iB'][0]:.15f}f")
        print(f"#define ADC_IB_B        {results['iB'][1]:.9f}f")
    if 'iR' in results:
        print(f"#define ADC_IREF_K      {results['iR'][0]:.15f}f")
        print(f"#define ADC_IREF_B      {results['iR'][1]:.9f}f")

if __name__ == '__main__':
    main()
