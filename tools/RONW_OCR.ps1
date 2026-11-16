# RONW_OCR.ps1 - reads text from a screen rectangle with the built-in Windows OCR.
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File RONW_OCR.ps1 X Y W H [Mode]
#   Mode normal (default): the picture as it is, enlarged 2x.
#   Mode white           : only the WHITE pixels, as black text on white, enlarged 3x.
#                          Game text (white with a dark outline on a busy scene)
#                          reads far better this way.
#   Mode both            : both of the above, results combined.
# Prints one line per word: W|text|x|y|width|height (screen pixels).
# On failure prints a single line starting with OCRERROR:
param([int]$X, [int]$Y, [int]$W, [int]$H, [string]$Mode = "normal")

try {
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public class RonwOcrTools
{
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();

    // Black where the source is white-ish, white everywhere else.
    public static Bitmap WhiteMask(Bitmap src)
    {
        int w = src.Width, h = src.Height;
        Bitmap dst = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        BitmapData a = src.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        BitmapData b = dst.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        byte[] s = new byte[a.Stride * h];
        byte[] d = new byte[b.Stride * h];
        Marshal.Copy(a.Scan0, s, 0, s.Length);
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                int i = y * a.Stride + x * 4;
                int bl = s[i], g = s[i + 1], r = s[i + 2];
                int mn = Math.Min(r, Math.Min(g, bl)), mx = Math.Max(r, Math.Max(g, bl));
                byte v = (mn >= 205 && (mx - mn) <= 45) ? (byte)0 : (byte)255;
                int j = y * b.Stride + x * 4;
                d[j] = v; d[j + 1] = v; d[j + 2] = v; d[j + 3] = 255;
            }
        Marshal.Copy(d, 0, b.Scan0, d.Length);
        src.UnlockBits(a);
        dst.UnlockBits(b);
        return dst;
    }
}
"@
    [RonwOcrTools]::SetProcessDPIAware() | Out-Null

    $null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Await($operation, $resultType) {
        $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
        $task.Wait(-1) | Out-Null
        $task.Result
    }

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { throw "No Windows OCR language is installed (Settings > Time & language > Language)." }

    # Enlarges a bitmap, runs OCR and prints its words in screen coordinates.
    function Read-Words($bitmap, [int]$factor) {
        $big = New-Object System.Drawing.Bitmap ($W * $factor), ($H * $factor)
        $g = [System.Drawing.Graphics]::FromImage($big)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($bitmap, 0, 0, $W * $factor, $H * $factor)
        $g.Dispose()

        $ms = New-Object System.IO.MemoryStream
        $big.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $ms.Position = 0
        $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $soft = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($soft)) ([Windows.Media.Ocr.OcrResult])

        foreach ($line in $result.Lines) {
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                $wx = $X + [int][math]::Round($r.X / $factor)
                $wy = $Y + [int][math]::Round($r.Y / $factor)
                $ww = [int][math]::Round($r.Width / $factor)
                $wh = [int][math]::Round($r.Height / $factor)
                Write-Output ("W|" + $word.Text + "|" + $wx + "|" + $wy + "|" + $ww + "|" + $wh)
            }
        }
    }

    $shot = New-Object System.Drawing.Bitmap $W, $H
    $g = [System.Drawing.Graphics]::FromImage($shot)
    $g.CopyFromScreen($X, $Y, 0, 0, $shot.Size)
    $g.Dispose()

    $mode = $Mode.ToLower()
    if ($mode -eq "normal" -or $mode -eq "both") { Read-Words $shot 2 }
    if ($mode -eq "white" -or $mode -eq "both") { Read-Words ([RonwOcrTools]::WhiteMask($shot)) 3 }
}
catch {
    Write-Output ("OCRERROR: " + $_.Exception.Message)
}
