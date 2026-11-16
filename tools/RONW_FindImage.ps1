# RONW_FindImage.ps1 - finds a small icon inside a screen rectangle.
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File RONW_FindImage.ps1 X Y W H "template.png" Threshold ScaleHint [MaskType] [MaxMatches]
#
# Only one colour class of the icon is compared, so a changed background does
# not matter. MaskType "white" (default) = white glyphs; "blue" = blue shapes
# (e.g. round blue buttons). Several sizes around ScaleHint are tried.
# Output, one line per match (best first, at most MaxMatches, default 1):
#   IMG|x|y|w|h|score     match at or above Threshold (screen pixels)
#   IMGNONE|score         nothing good enough (score = best seen, 0 if far off)
#   OCRERROR: message     failure
param([int]$X, [int]$Y, [int]$W, [int]$H, [string]$Template, [double]$Threshold, [double]$ScaleHint,
      [string]$MaskType = "white", [int]$MaxMatches = 1)

try {
    Add-Type -AssemblyName System.Drawing
    Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class RonwImg
{
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();

    static bool IsWhite(int r, int g, int b)
    {
        int mx = Math.Max(r, Math.Max(g, b));
        int mn = Math.Min(r, Math.Min(g, b));
        return mn >= 190 && (mx - mn) <= 45;
    }

    static bool IsBlue(int r, int g, int b)
    {
        return b >= 150 && (b - r) >= 60 && (b - g) >= 15;
    }

    static bool[] Mask(Bitmap bmp, string type, out int w, out int h)
    {
        bool blue = (type == "blue");
        w = bmp.Width; h = bmp.Height;
        bool[] m = new bool[w * h];
        BitmapData d = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        byte[] buf = new byte[d.Stride * h];
        Marshal.Copy(d.Scan0, buf, 0, buf.Length);
        bmp.UnlockBits(d);
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                int i = y * d.Stride + x * 4;
                m[y * w + x] = blue ? IsBlue(buf[i + 2], buf[i + 1], buf[i]) : IsWhite(buf[i + 2], buf[i + 1], buf[i]);
            }
        return m;
    }

    // Returns "best;score|x|y|w|h;score|x|y|w|h;..." : the best score seen and up
    // to maxMatches separate matches at or above the threshold (score =
    // intersection over union of the masked pixels). Positions that cannot reach
    // 60% of the threshold are skipped early, so a full-window search stays fast.
    public static string Find(Bitmap screen, Bitmap tpl, double[] scales, double threshold, string type, int maxMatches)
    {
        int sw, sh, tw, th;
        bool[] S = Mask(screen, type, out sw, out sh);
        bool[] T0 = Mask(tpl, type, out tw, out th);

        // Integral image of the white pixels: counts white pixels in any box.
        int stride = sw + 1;
        int[] I = new int[stride * (sh + 1)];
        for (int y = 0; y < sh; y++)
        {
            int row = 0;
            for (int x = 0; x < sw; x++)
            {
                if (S[y * sw + x]) row++;
                I[(y + 1) * stride + x + 1] = I[y * stride + x + 1] + row;
            }
        }

        double diag = threshold * 0.6;
        double best = 0;
        List<double[]> cands = new List<double[]>();

        foreach (double sc in scales)
        {
            int w = (int)Math.Round(tw * sc), h = (int)Math.Round(th * sc);
            if (w < 6 || h < 6 || w > sw || h > sh) continue;

            List<int> lx = new List<int>(), ly = new List<int>();
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    int sy = Math.Min(th - 1, (int)(y / sc));
                    int sx = Math.Min(tw - 1, (int)(x / sc));
                    if (T0[sy * tw + sx]) { lx.Add(x); ly.Add(y); }
                }
            int cnt = lx.Count;
            if (cnt < 12) continue;
            int[] dx = lx.ToArray(), dy = ly.ToArray();
            int need = (int)Math.Ceiling(diag * cnt / (1 + diag));
            int allowedMiss = cnt - need;

            for (int oy = 0; oy <= sh - h; oy++)
                for (int ox = 0; ox <= sw - w; ox++)
                {
                    int inter = 0, miss = 0;
                    for (int k = 0; k < cnt; k++)
                    {
                        if (S[(oy + dy[k]) * sw + ox + dx[k]]) inter++;
                        else if (++miss > allowedMiss) break;
                    }
                    if (miss > allowedMiss) continue;

                    int sW = I[(oy + h) * stride + ox + w] - I[oy * stride + ox + w]
                           - I[(oy + h) * stride + ox] + I[oy * stride + ox];
                    int uni = cnt + sW - inter;
                    double score = uni == 0 ? 0 : (double)inter / uni;
                    if (score > best) best = score;
                    if (score >= threshold) cands.Add(new double[] { score, ox, oy, w, h });
                }
        }

        cands.Sort(delegate(double[] a, double[] b) { return b[0].CompareTo(a[0]); });
        List<double[]> kept = new List<double[]>();
        foreach (double[] c in cands)
        {
            if (kept.Count >= maxMatches) break;
            bool near = false;
            foreach (double[] k in kept)
                if (Math.Abs(c[1] - k[1]) < 0.6 * c[3] && Math.Abs(c[2] - k[2]) < 0.6 * c[4]) { near = true; break; }
            if (!near) kept.Add(c);
        }

        string result = best.ToString("0.000", CultureInfo.InvariantCulture);
        foreach (double[] k in kept)
            result += string.Format(CultureInfo.InvariantCulture, ";{0:0.000}|{1}|{2}|{3}|{4}", k[0], k[1], k[2], k[3], k[4]);
        return result;
    }
}
"@
    [RonwImg]::SetProcessDPIAware() | Out-Null

    if (-not (Test-Path -LiteralPath $Template)) { throw "Template image not found: $Template" }
    $tpl = New-Object System.Drawing.Bitmap $Template

    $shot = New-Object System.Drawing.Bitmap $W, $H
    $g = [System.Drawing.Graphics]::FromImage($shot)
    $g.CopyFromScreen($X, $Y, 0, 0, $shot.Size)
    $g.Dispose()

    if ($ScaleHint -le 0) { $ScaleHint = 1.0 }
    [double[]]$scales = @(($ScaleHint * 0.85), ($ScaleHint * 0.92), $ScaleHint, ($ScaleHint * 1.08), ($ScaleHint * 1.18))

    if ($MaxMatches -lt 1) { $MaxMatches = 1 }
    $parts = ([RonwImg]::Find($shot, $tpl, $scales, $Threshold, $MaskType.ToLower(), $MaxMatches)).Split(';')
    if ($parts.Count -le 1) {
        Write-Output ("IMGNONE|" + $parts[0])
    }
    else {
        for ($i = 1; $i -lt $parts.Count; $i++) {
            $p = $parts[$i].Split('|')
            Write-Output ("IMG|" + ($X + [int]$p[1]) + "|" + ($Y + [int]$p[2]) + "|" + $p[3] + "|" + $p[4] + "|" + $p[0])
        }
    }
}
catch {
    Write-Output ("OCRERROR: " + $_.Exception.Message)
}
