package com.novadial.phone.views

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.SweepGradient
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.animation.DecelerateInterpolator
import kotlin.math.cos
import kotlin.math.sin

/**
 * Native Android recreation of the Ava007 rotary selector reference.
 *
 * This is deliberately display-only: selecting PRIME / SELECT / ULTRA does not
 * change Telnyx registration or call behavior.
 */
class Ava007RotarySelectorView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val modes = listOf("PRIME", "SELECT", "ULTRA")
    private var selectedIndex = 0
    private var textureRotation = 0f
    private var spinProgress = 0f
    private var spinning = false

    private val density = resources.displayMetrics.density
    private fun dp(value: Float) = value * density

    private val housingPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(2f)
        color = Color.rgb(54, 54, 54)
    }
    private val texturePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
        color = Color.rgb(48, 48, 48)
        alpha = 150
    }
    private val glassPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val indicatorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 62, 62)
        setShadowLayer(dp(8f), 0f, 0f, Color.rgb(255, 35, 35))
    }
    private val numberPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 62, 62)
        typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
        textSize = dp(11f)
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
        textSize = dp(31f)
    }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(136, 136, 136)
        typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
        textSize = dp(9f)
        textAlign = Paint.Align.CENTER
    }
    private val shadePaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val clipPath = Path()
    private val rect = RectF()

    init {
        setLayerType(LAYER_TYPE_SOFTWARE, null)
        isClickable = true
        contentDescription = "Rotary mode selector. Current mode PRIME. Tap to spin."
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = dp(240f).toInt()
        val desiredHeight = dp(282f).toInt()
        val measuredWidth = resolveSize(desiredWidth, widthMeasureSpec)
        val measuredHeight = resolveSize(desiredHeight, heightMeasureSpec)
        setMeasuredDimension(measuredWidth, measuredHeight)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val centerX = width / 2f
        val boxWidth = minOf(dp(200f), width - dp(12f))
        val boxHeight = dp(240f)
        val left = centerX - boxWidth / 2f
        val top = dp(34f)
        val right = left + boxWidth
        val bottom = top + boxHeight
        val radius = dp(29f)
        rect.set(left, top, right, bottom)

        hintPaint.alpha = (205 + 35 * (0.5f + 0.5f * sin(System.nanoTime() / 500_000_000.0)).toFloat()).toInt()
        canvas.drawText("T A P   T O   S P I N", centerX, dp(13f), hintPaint)

        housingPaint.color = Color.rgb(17, 17, 17)
        housingPaint.setShadowLayer(dp(18f), 0f, dp(14f), Color.argb(150, 0, 0, 0))
        canvas.drawRoundRect(rect, radius, radius, housingPaint)
        housingPaint.clearShadowLayer()
        canvas.drawRoundRect(rect, radius, radius, borderPaint)

        val saveClip = canvas.save()
        clipPath.reset()
        clipPath.addRoundRect(rect, radius, radius, Path.Direction.CW)
        canvas.clipPath(clipPath)

        // Repeating radial grooves give the right side a machined, brushed-metal wheel texture.
        val wheelCenterX = right + dp(38f)
        val wheelCenterY = top + boxHeight / 2f
        val outerRadius = dp(190f)
        for (i in 0 until 36) {
            val angle = Math.toRadians((i * 10.0) + textureRotation * 0.15)
            val x1 = wheelCenterX + cos(angle).toFloat() * dp(42f)
            val y1 = wheelCenterY + sin(angle).toFloat() * dp(42f)
            val x2 = wheelCenterX + cos(angle).toFloat() * outerRadius
            val y2 = wheelCenterY + sin(angle).toFloat() * outerRadius
            texturePaint.alpha = if (i % 2 == 0) 100 else 45
            canvas.drawLine(x1, y1, x2, y2, texturePaint)
        }

        // Subtle inset vignette.
        shadePaint.shader = SweepGradient(
            centerX, wheelCenterY,
            intArrayOf(
                Color.argb(0, 255, 255, 255),
                Color.argb(22, 255, 255, 255),
                Color.argb(0, 0, 0, 0),
                Color.argb(55, 0, 0, 0),
                Color.argb(0, 255, 255, 255)
            ),
            floatArrayOf(0f, 0.16f, 0.45f, 0.76f, 1f)
        )
        canvas.drawRoundRect(rect, radius, radius, shadePaint)
        shadePaint.shader = null

        val centerY = top + boxHeight / 2f
        val labelX = left + dp(40f)
        val offsets = floatArrayOf(-1f, 0f, 1f)
        offsets.forEach { offset ->
            val modeIndex = (selectedIndex + offset.toInt() + modes.size) % modes.size
            val distanceFromFocus = kotlin.math.abs(offset - spinProgress)
            val isSelected = distanceFromFocus < 0.34f
            val y = centerY + (offset - spinProgress) * dp(67f)
            val angle = (offset - spinProgress) * -30f
            val alpha = if (isSelected) 255 else (28 + (1f - distanceFromFocus.coerceAtMost(1f)) * 34f).toInt()
            val save = canvas.save()
            canvas.rotate(angle, right + dp(75f), y)
            numberPaint.alpha = if (isSelected) 255 else 95
            labelPaint.alpha = alpha
            labelPaint.textSize = if (isSelected) dp(31f) else dp(27f)
            labelPaint.setShadowLayer(if (isSelected) dp(12f) else 0f, 0f, 0f, Color.argb(65, 255, 255, 255))
            val number = "%02d".format(modeIndex + 1)
            canvas.drawText(number, labelX, y - dp(11f), numberPaint)
            canvas.drawText(modes[modeIndex], labelX, y + dp(20f), labelPaint)
            labelPaint.clearShadowLayer()
            canvas.restoreToCount(save)
        }

        // Red position marker and a faint horizontal guide.
        val markerY = centerY
        texturePaint.alpha = 45
        canvas.drawLine(left + dp(20f), markerY, right - dp(10f), markerY, texturePaint)
        canvas.drawCircle(left + dp(15f), markerY, dp(3f), indicatorPaint)

        // Glass reflection, kept translucent so the wheel texture remains visible.
        glassPaint.shader = android.graphics.LinearGradient(
            left, top, right, bottom,
            intArrayOf(Color.argb(34, 255, 255, 255), Color.argb(0, 255, 255, 255), Color.argb(28, 0, 0, 0)),
            null,
            android.graphics.Shader.TileMode.CLAMP
        )
        canvas.drawRoundRect(rect, radius, radius, glassPaint)
        glassPaint.shader = null
        canvas.restoreToCount(saveClip)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> return true
            MotionEvent.ACTION_UP -> {
                if (isEnabled) {
                    if (spinning) return true
                    spinning = true
                    val animator = ValueAnimator.ofFloat(0f, 1f)
                    animator.duration = 620L
                    animator.interpolator = DecelerateInterpolator(1.8f)
                    animator.addUpdateListener {
                        spinProgress = it.animatedValue as Float
                        textureRotation += 1.2f
                        invalidate()
                    }
                    animator.addListener(object : android.animation.AnimatorListenerAdapter() {
                        override fun onAnimationEnd(animation: android.animation.Animator) {
                            selectedIndex = (selectedIndex + 1) % modes.size
                            spinProgress = 0f
                            spinning = false
                            contentDescription = "Rotary mode selector. Current mode ${modes[selectedIndex]}. Tap to spin."
                            invalidate()
                        }

                        override fun onAnimationCancel(animation: android.animation.Animator) {
                            spinProgress = 0f
                            spinning = false
                        }
                    })
                    animator.start()
                    performClick()
                }
                return true
            }
            MotionEvent.ACTION_CANCEL -> return true
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

}
