import os
import csv
import re
import math

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
    # Returns a list of values for the given index from the CSV
    with open(filepath, 'r') as f:
        content = f.read()
        # Regex to find tempData array values
        # Pattern: 2,"\[index\]",([\d\.]+),
        pattern = re.compile(r'^\s*2,"\[{}\]",([\d\.]+),'.format(index), re.MULTILINE)
        matches = pattern.findall(content)
        if matches:
            float_vals = [float(x) for x in matches]
            return sum(float_vals) / len(float_vals)
    return None

def main():
    calib_dir = r'd:\code\rm\supercap\supercap_25_claude\PowerControlBoard_Software_FieldVersion\debug\calibration'
    files = os.listdir(calib_dir)
    
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
    
    for filename in files:
        if not filename.endswith('.csv'):
            continue
            
        filepath = os.path.join(calib_dir, filename)
        
        # Determine targets
        targets = {} # channel -> target_value
        
        # Parse filename
        # 1. AxxV or Axxv: No load, Voltage xx
        m_av = re.match(r'A([\d\.]+)V\.csv', filename, re.IGNORECASE)
        # 2. AxxA: Load on REF, Current xx
        m_aa = re.match(r'A([\d\.]+)A\.csv', filename, re.IGNORECASE)
        # 3. BxxAyyV: Load on CAP, Current xx, Voltage yy
        m_b = re.match(r'B([\d\.]+)A([\d\.]+)V\.csv', filename, re.IGNORECASE)
        
        if m_av:
            vol = float(m_av.group(1))
            targets['vA'] = vol
            targets['iA'] = 0.0
            targets['iB'] = 0.0
            targets['iR'] = 0.0
            # vB?
            
        elif m_aa:
            curr = float(m_aa.group(1))
            targets['vA'] = 24.0
            targets['iA'] = 0.0 # iA does not seem to measure REF current based on data
            targets['iR'] = -curr # REF current negative (out)
            targets['iB'] = 0.0
            
        elif m_b:
            curr = float(m_b.group(1))
            vol = float(m_b.group(2))
            targets['vA'] = 24.0
            targets['vB'] = vol
            targets['iB'] = curr # CAP current positive (out? wait)
            # In B1.5A..., iB was 1.49. So iB target should be positive.
            targets['iR'] = 0.0
            
            # Estimate iA target
            # P_in = P_out / Efficiency
            # vA * iA = (vB * iB) / 0.9 (Assume 90% efficiency)
            # iA = (vB * iB) / (vA * 0.9)
            if targets['vA'] > 0:
                targets['iA'] = (vol * curr) / (targets['vA'] * 0.9)
            
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
