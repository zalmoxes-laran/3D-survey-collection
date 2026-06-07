#!/usr/bin/env python3
"""
Generate architecturally-correct SVG templates for 3D Survey Collection orthogonal renders.

Produces two families of templates:
- Family A (Fixed Sheet): Always A3, images fill available space, high-res for screen zoom
- Family B (Fixed Scale): True metric scale on paper, paper size varies to fit

Usage:
    python generate_svg_templates.py              # Generate all templates
    python generate_svg_templates.py --family A   # Only Family A
    python generate_svg_templates.py --family B   # Only Family B
    python generate_svg_templates.py --id FIXED_A3_50cm  # Single template
"""

import os
import argparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAPER_SIZES = {
    'A0': (1189, 841),
    'A1': (841, 594),
    'A2': (594, 420),
    'A3': (420, 297),
}

MARGINS = {'top': 15, 'left': 15, 'right': 15, 'bottom': 30}
GUTTER = 5

# Style
BG_COLOR = '#333132'
STROKE_COLOR = '#ffffff'
TEXT_COLOR = '#fffefe'
STROKE_WIDTH = 0.5

# ---------------------------------------------------------------------------
# Template configurations
# ---------------------------------------------------------------------------

FAMILY_A_CONFIGS = [
    {'id': 'FIXED_A3_50cm',         'paper': 'A3', 'obj_m': 0.5, 'S': 80,  'family': 'A'},
    {'id': 'FIXED_A3_50cm_compact', 'paper': 'A3', 'obj_m': 0.5, 'S': 50,  'family': 'A'},
    {'id': 'FIXED_A3_1m',           'paper': 'A3', 'obj_m': 1.0, 'S': 80,  'family': 'A'},
    {'id': 'FIXED_A3_1m_compact',   'paper': 'A3', 'obj_m': 1.0, 'S': 50,  'family': 'A'},
    {'id': 'FIXED_A3_2m',           'paper': 'A3', 'obj_m': 2.0, 'S': 80,  'family': 'A'},
    {'id': 'FIXED_A3_2m_compact',   'paper': 'A3', 'obj_m': 2.0, 'S': 40,  'family': 'A'},
]

FAMILY_B_CONFIGS = [
    {'id': 'SCALE_1-5_A2_50cm',  'paper': 'A2', 'obj_m': 0.5, 'scale_denom': 5,  'family': 'B'},
    {'id': 'SCALE_1-2_A0_50cm',  'paper': 'A0', 'obj_m': 0.5, 'scale_denom': 2,  'family': 'B'},
    {'id': 'SCALE_1-10_A2_1m',   'paper': 'A2', 'obj_m': 1.0, 'scale_denom': 10, 'family': 'B'},
    {'id': 'SCALE_1-5_A0_1m',    'paper': 'A0', 'obj_m': 1.0, 'scale_denom': 5,  'family': 'B'},
    {'id': 'SCALE_1-20_A2_2m',   'paper': 'A2', 'obj_m': 2.0, 'scale_denom': 20, 'family': 'B'},
    {'id': 'SCALE_1-10_A0_2m',   'paper': 'A0', 'obj_m': 2.0, 'scale_denom': 10, 'family': 'B'},
]

ALL_CONFIGS = FAMILY_A_CONFIGS + FAMILY_B_CONFIGS

# Third-angle projection: Right of Front = Right view, Top of Front = Top view
# Image mapping is hardcoded in orthogonal_render.py:
#   _ref_image1=FR, _ref_image2=BA, _ref_image3=RI, _ref_image4=LE, _ref_image5=TO, _ref_image6=BO
VIEWS = [
    {'idx': 1, 'code': 'FR', 'label': 'Front (FR)',  'col': 2, 'row': 1},
    {'idx': 2, 'code': 'BA', 'label': 'Back (BA)',   'col': 0, 'row': 1},
    {'idx': 3, 'code': 'RI', 'label': 'Right (RI)',  'col': 3, 'row': 1},
    {'idx': 4, 'code': 'LE', 'label': 'Left (LE)',   'col': 1, 'row': 1},
    {'idx': 5, 'code': 'TO', 'label': 'Top (TO)',    'col': 2, 'row': 0},
    {'idx': 6, 'code': 'BO', 'label': 'Bottom (BO)', 'col': 2, 'row': 2},
]

# ---------------------------------------------------------------------------
# Layout computation
# ---------------------------------------------------------------------------

def compute_layout(paper_key, S):
    """Compute all positions for the cross layout.

    Returns dict with paper dimensions, column X positions, row Y positions.
    """
    pw, ph = PAPER_SIZES[paper_key]
    ml, mt, mr, mb = MARGINS['left'], MARGINS['top'], MARGINS['right'], MARGINS['bottom']
    g = GUTTER

    col_x = [
        ml,                    # col 0: Back
        ml + S + g,            # col 1: Left
        ml + 2 * S + 2 * g,   # col 2: Front
        ml + 3 * S + 3 * g,   # col 3: Right
    ]
    row_y = [
        mt,                    # row 0: Top
        mt + S + g,            # row 1: Main
        mt + 2 * S + 2 * g,   # row 2: Bottom
    ]

    total_w = col_x[3] + S + mr
    total_h = row_y[2] + S + mb

    if total_w > pw or total_h > ph:
        print(f"  WARNING: layout overflow for S={S}mm on {paper_key} "
              f"(need {total_w:.0f}x{total_h:.0f}, have {pw}x{ph})")

    return {
        'pw': pw, 'ph': ph, 'S': S,
        'col_x': col_x, 'row_y': row_y,
        'total_w': total_w, 'total_h': total_h,
    }


def get_image_size(config):
    """Return image size S in mm for a given config."""
    if 'S' in config:
        return config['S']
    return config['obj_m'] * 1000 / config['scale_denom']


def get_scale_denom(config):
    """Return the scale denominator (may be non-integer for Family A)."""
    if 'scale_denom' in config:
        return config['scale_denom']
    S = config['S']
    obj_mm = config['obj_m'] * 1000
    return obj_mm / S

# ---------------------------------------------------------------------------
# SVG generation helpers
# ---------------------------------------------------------------------------

def fmt(v):
    """Format a float, stripping trailing zeros."""
    if v == int(v):
        return str(int(v))
    return f'{v:.4f}'.rstrip('0').rstrip('.')


def svg_scale_bar(obj_m, S, x_start, y_start, bar_height=3):
    """Generate SVG elements for the architectural scale bar.

    5 divisions representing the full object size.
    """
    obj_mm = obj_m * 1000
    scale_denom_actual = obj_mm / S
    # Total bar length on paper = S (represents full object size)
    bar_length = S
    div_width = bar_length / 5
    div_real = obj_mm / 5  # real-world size per division

    # Choose unit for labels
    if obj_m <= 1.0:
        unit = 'cm'
        divisor = 10  # mm to cm
    else:
        unit = 'm'
        divisor = 1000  # mm to m

    parts = []

    # Rectangles
    for i in range(5):
        rx = x_start + i * div_width
        fill = STROKE_COLOR if i % 2 == 0 else 'none'
        parts.append(
            f'    <rect x="{fmt(rx)}" y="{fmt(y_start)}" '
            f'width="{fmt(div_width)}" height="{fmt(bar_height)}" '
            f'style="fill:{fill};stroke:{STROKE_COLOR};stroke-width:0.3"/>'
        )

    # Labels
    label_y = y_start + bar_height + 3  # 3mm below bar
    font_size = 2.5
    for i in range(6):
        lx = x_start + i * div_width
        real_val = i * div_real / divisor
        # Format label
        if real_val == int(real_val):
            label = str(int(real_val))
        else:
            label = f'{real_val:.1f}'
        if i == 5:
            label += f' {unit}'

        anchor = 'start' if i == 0 else ('end' if i == 5 else 'middle')
        parts.append(
            f'    <text x="{fmt(lx)}" y="{fmt(label_y)}" '
            f'style="font-family:sans-serif;font-size:{font_size}px;'
            f'fill:{TEXT_COLOR};text-anchor:{anchor}">{label}</text>'
        )

    # Scale ratio text
    if scale_denom_actual == int(scale_denom_actual):
        scale_text = f'1:{int(scale_denom_actual)}'
    else:
        scale_text = f'1:{scale_denom_actual:.2f}'

    parts.append(
        f'    <text x="{fmt(x_start + bar_length / 2)}" y="{fmt(label_y + 4)}" '
        f'style="font-family:sans-serif;font-size:3px;'
        f'fill:{TEXT_COLOR};text-anchor:middle">Scala {scale_text}</text>'
    )

    return '\n'.join(parts)


def svg_title_block(pw, ph, scale_text, paper_key):
    """Generate the cartiglio (title block) in the bottom margin area."""
    mb = MARGINS['bottom']
    ml = MARGINS['left']
    mr = MARGINS['right']
    block_y = ph - mb + 2  # 2mm below the image area
    block_h = mb - 4       # leave 2mm padding top and bottom
    block_w = pw - ml - mr

    parts = []

    # Title block border
    parts.append(
        f'    <rect x="{fmt(ml)}" y="{fmt(block_y)}" '
        f'width="{fmt(block_w)}" height="{fmt(block_h)}" '
        f'style="fill:none;stroke:{STROKE_COLOR};stroke-width:{STROKE_WIDTH}"/>'
    )

    # Logo placeholder (left side, 20x20mm)
    logo_x = ml + 2
    logo_y = block_y + (block_h - 20) / 2
    if block_h >= 22:
        parts.append(
            f'    <image xlink:href="_ref_logo" '
            f'x="{fmt(logo_x)}" y="{fmt(logo_y)}" width="20" height="20" '
            f'preserveAspectRatio="xMidYMid meet"/>'
        )
        text_x = logo_x + 25
    else:
        parts.append(
            f'    <image xlink:href="_ref_logo" '
            f'x="{fmt(logo_x)}" y="{fmt(block_y + 1)}" '
            f'width="{fmt(block_h - 2)}" height="{fmt(block_h - 2)}" '
            f'preserveAspectRatio="xMidYMid meet"/>'
        )
        text_x = logo_x + block_h + 3

    # Font sizes proportional to paper
    fs_title = 5 if pw >= 841 else (4 if pw >= 594 else 3.5)
    fs_subtitle = 4 if pw >= 841 else (3.5 if pw >= 594 else 3)
    fs_info = 3 if pw >= 841 else 2.5

    # Project title
    parts.append(
        f'    <text x="{fmt(text_x)}" y="{fmt(block_y + fs_title + 2)}" '
        f'style="font-family:sans-serif;font-size:{fs_title}px;'
        f'fill:{TEXT_COLOR}">_3dsctitolo</text>'
    )

    # Object name
    parts.append(
        f'    <text x="{fmt(text_x)}" y="{fmt(block_y + fs_title + fs_subtitle + 5)}" '
        f'style="font-family:sans-serif;font-size:{fs_subtitle}px;'
        f'fill:{TEXT_COLOR};font-weight:bold">_3dscnomeblocco</text>'
    )

    # Dimensions
    parts.append(
        f'    <text x="{fmt(text_x)}" y="{fmt(block_y + fs_title + fs_subtitle + fs_info + 8)}" '
        f'style="font-family:sans-serif;font-size:{fs_info}px;'
        f'fill:{TEXT_COLOR}">_3dscmisure</text>'
    )

    # Right side: scale and paper info
    right_x = ml + block_w - 3
    parts.append(
        f'    <text x="{fmt(right_x)}" y="{fmt(block_y + fs_title + 2)}" '
        f'style="font-family:sans-serif;font-size:{fs_title}px;'
        f'fill:{TEXT_COLOR};text-anchor:end">{scale_text}</text>'
    )
    parts.append(
        f'    <text x="{fmt(right_x)}" y="{fmt(block_y + fs_title + fs_info + 5)}" '
        f'style="font-family:sans-serif;font-size:{fs_info}px;'
        f'fill:{TEXT_COLOR};text-anchor:end">{paper_key}</text>'
    )

    return '\n'.join(parts)


def generate_svg(config):
    """Generate complete SVG content for a template configuration."""
    S = get_image_size(config)
    scale_d = get_scale_denom(config)
    paper_key = config['paper']
    layout = compute_layout(paper_key, S)
    pw, ph = layout['pw'], layout['ph']
    col_x = layout['col_x']
    row_y = layout['row_y']

    # Scale text
    if scale_d == int(scale_d):
        scale_text = f'Scala 1:{int(scale_d)}'
    else:
        scale_text = f'Scala 1:{scale_d:.2f}'

    # Font size for view labels
    fs_label = 5 if pw >= 841 else (3.5 if pw >= 594 else 3)

    # --- Build SVG ---
    parts = []

    # XML declaration and SVG root
    parts.append(f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   width="{pw}mm"
   height="{ph}mm"
   viewBox="0 0 {pw} {ph}"
   id="svg_root"
   version="1.1"
   inkscape:version="1.2.1 (9c6d41e410, 2022-07-14)"
   sodipodi:docname="{config['id']}.svg"
   xml:space="preserve"
   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
   xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
   xmlns:xlink="http://www.w3.org/1999/xlink"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:cc="http://creativecommons.org/ns#"
   xmlns:dc="http://purl.org/dc/elements/1.1/">''')

    # Defs: clip paths
    parts.append('  <defs id="defs_clips">')
    for v in VIEWS:
        vx = col_x[v['col']]
        vy = row_y[v['row']]
        parts.append(
            f'    <clipPath id="clip_view{v["idx"]}" clipPathUnits="userSpaceOnUse">\n'
            f'      <rect x="{fmt(vx)}" y="{fmt(vy)}" '
            f'width="{fmt(S)}" height="{fmt(S)}"/>\n'
            f'    </clipPath>'
        )
    parts.append('  </defs>')

    # Named view (Inkscape metadata)
    parts.append('''  <sodipodi:namedview
     id="namedview"
     pagecolor="#ffffff"
     bordercolor="#666666"
     borderopacity="1.0"
     inkscape:pageopacity="0.0"
     inkscape:pageshadow="2"
     inkscape:document-units="mm"
     inkscape:current-layer="layer_images"
     showgrid="true"
     units="mm">
    <inkscape:grid
       type="xygrid"
       id="grid1"
       empspacing="5"
       visible="true"
       enabled="true"
       snapvisiblegridlinesonly="true"
       spacingx="1"
       spacingy="1"
       units="mm"/>
  </sodipodi:namedview>''')

    # Metadata
    parts.append('''  <metadata id="metadata">
    <rdf:RDF>
      <cc:Work rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type rdf:resource="http://purl.org/dc/dcmitype/StillImage"/>
      </cc:Work>
    </rdf:RDF>
  </metadata>''')

    # Layer: Sfondo (Background)
    parts.append(f'''  <g inkscape:groupmode="layer" id="layer_bg" inkscape:label="Sfondo" style="display:inline">
    <rect x="0" y="0" width="{pw}" height="{ph}"
          style="fill:{BG_COLOR};fill-opacity:1;stroke:none"/>
  </g>''')

    # Layer: Cornici (Frames) — white borders around each image cell
    parts.append('  <g inkscape:groupmode="layer" id="layer_frames" inkscape:label="Cornici" style="display:inline">')
    for v in VIEWS:
        vx = col_x[v['col']]
        vy = row_y[v['row']]
        parts.append(
            f'    <rect x="{fmt(vx)}" y="{fmt(vy)}" '
            f'width="{fmt(S)}" height="{fmt(S)}" '
            f'style="fill:none;stroke:{STROKE_COLOR};stroke-width:{STROKE_WIDTH}"/>'
        )
    parts.append('  </g>')

    # Layer: Immagini (Images)
    parts.append('  <g inkscape:groupmode="layer" id="layer_images" inkscape:label="Immagini" style="display:inline">')
    for v in VIEWS:
        vx = col_x[v['col']]
        vy = row_y[v['row']]
        parts.append(
            f'    <image\n'
            f'       xlink:href="_ref_image{v["idx"]}"\n'
            f'       x="{fmt(vx)}" y="{fmt(vy)}"\n'
            f'       width="{fmt(S)}" height="{fmt(S)}"\n'
            f'       clip-path="url(#clip_view{v["idx"]})"\n'
            f'       preserveAspectRatio="xMidYMid meet"\n'
            f'       id="image_view{v["idx"]}"/>'
        )
    parts.append('  </g>')

    # Layer: Etichette (Labels)
    parts.append('  <g inkscape:groupmode="layer" id="layer_labels" inkscape:label="Etichette" style="display:inline">')
    for v in VIEWS:
        vx = col_x[v['col']]
        vy = row_y[v['row']]
        # Label above the image cell
        lx = vx + S / 2
        ly = vy - 1.5  # 1.5mm above the cell
        parts.append(
            f'    <text x="{fmt(lx)}" y="{fmt(ly)}" '
            f'style="font-family:sans-serif;font-size:{fs_label}px;'
            f'fill:{TEXT_COLOR};text-anchor:middle">{v["label"]}</text>'
        )
    parts.append('  </g>')

    # Layer: Scala (Scale bar)
    # Position: in the title block area, centered horizontally
    scale_bar_y = ph - MARGINS['bottom'] + 2
    # Place scale bar above the title block text
    # Use the center area of the paper
    scale_bar_x = pw / 2 - S / 2
    parts.append('  <g inkscape:groupmode="layer" id="layer_scale" inkscape:label="Scala" style="display:inline">')
    parts.append(svg_scale_bar(config['obj_m'], S, scale_bar_x, scale_bar_y))
    parts.append('  </g>')

    # Layer: Cartiglio (Title block)
    # Push it below the scale bar
    parts.append('  <g inkscape:groupmode="layer" id="layer_titleblock" inkscape:label="Cartiglio" style="display:inline">')
    parts.append(svg_title_block(pw, ph, scale_text, paper_key))
    parts.append('  </g>')

    # Close SVG
    parts.append('</svg>')

    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate SVG templates for 3DSC orthogonal renders')
    parser.add_argument('--family', choices=['A', 'B'], help='Generate only one family')
    parser.add_argument('--id', help='Generate only a single template by ID')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: svg_templates/ next to this script)')
    args = parser.parse_args()

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'svg_templates')

    os.makedirs(output_dir, exist_ok=True)

    # Select configs
    if args.id:
        configs = [c for c in ALL_CONFIGS if c['id'] == args.id]
        if not configs:
            print(f"ERROR: Template ID '{args.id}' not found. Available IDs:")
            for c in ALL_CONFIGS:
                print(f"  {c['id']}")
            return
    elif args.family == 'A':
        configs = FAMILY_A_CONFIGS
    elif args.family == 'B':
        configs = FAMILY_B_CONFIGS
    else:
        configs = ALL_CONFIGS

    print(f"Generating {len(configs)} template(s) into {output_dir}/\n")

    for config in configs:
        S = get_image_size(config)
        scale_d = get_scale_denom(config)
        print(f"  {config['id']}: paper={config['paper']}, obj={config['obj_m']}m, "
              f"S={S}mm, scale=1:{scale_d:.2f}")

        svg_content = generate_svg(config)
        filepath = os.path.join(output_dir, f"{config['id']}.svg")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"    -> {filepath}")

    print(f"\nDone. Generated {len(configs)} SVG template(s).")


if __name__ == '__main__':
    main()
