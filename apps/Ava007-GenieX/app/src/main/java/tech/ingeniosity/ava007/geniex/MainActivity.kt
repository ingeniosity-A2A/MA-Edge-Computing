package tech.ingeniosity.ava007.geniex

import android.app.Activity
import android.graphics.Typeface
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.geniex.sdk.GenieXSdk
import com.geniex.sdk.LlmWrapper
import com.geniex.sdk.ModelManagerWrapper
import com.geniex.sdk.bean.ChatMessage
import com.geniex.sdk.bean.GenerationConfig
import com.geniex.sdk.bean.HubSource
import com.geniex.sdk.bean.LlmCreateInput
import com.geniex.sdk.bean.LlmStreamResult
import com.geniex.sdk.bean.ModelConfig
import com.geniex.sdk.bean.ModelPullInput
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : Activity() {
    private val uiScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var status: TextView
    private lateinit var prompt: EditText
    private lateinit var output: TextView
    private lateinit var runButton: Button
    private var runJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        try {
            GenieXSdk.getInstance().init(applicationContext)
            status.text = "GenieX initialized. Model is downloaded on first run."
        } catch (error: Throwable) {
            status.text = "GenieX initialization failed: ${error.message}"
            runButton.isEnabled = false
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 28, 24, 24)
        }
        val heading = TextView(this).apply {
            text = "AVA-007 · GENIEX EDGE"
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
        }
        status = TextView(this).apply {
            text = "Initializing local runtime…"
            textSize = 14f
            setPadding(0, 16, 0, 16)
        }
        prompt = EditText(this).apply {
            hint = "Ask the on-device model"
            setText("Explain how local inference can support an edge node.")
            minLines = 2
            gravity = android.view.Gravity.TOP
        }
        runButton = Button(this).apply {
            text = "Download / Load Model and Run"
            setOnClickListener { runInference() }
        }
        output = TextView(this).apply {
            text = "Model output will appear here."
            textSize = 16f
            setPadding(0, 16, 0, 16)
        }
        val scroll = ScrollView(this).apply {
            addView(output)
        }
        root.addView(heading)
        root.addView(status)
        root.addView(prompt, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        root.addView(runButton)
        root.addView(scroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f
        ))
        setContentView(root)
    }

    private fun runInference() {
        if (runJob?.isActive == true) return
        runButton.isEnabled = false
        output.text = ""
        status.text = "Preparing model…"
        val userPrompt = prompt.text.toString().trim().ifBlank { "What can you do?" }

        runJob = uiScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    val modelName = MODEL_NAME
                    val existing = ModelManagerWrapper.getPaths(modelName)
                    if (existing == null) {
                        ModelManagerWrapper.pullFlow(
                            ModelPullInput(
                                model_name = modelName,
                                precision = "Q4_0",
                                hub = HubSource.HUGGINGFACE
                            )
                        ).collect { event ->
                            when (event) {
                                is ModelManagerWrapper.PullEvent.Progress ->
                                    runOnUiThread { status.text = "Downloading model…" }
                                ModelManagerWrapper.PullEvent.Completed ->
                                    runOnUiThread { status.text = "Model downloaded. Loading…" }
                                is ModelManagerWrapper.PullEvent.Error ->
                                    error("GenieX model download failed")
                            }
                        }
                    }

                    val paths = ModelManagerWrapper.getPaths(modelName)
                        ?: error("Model download completed but model paths are unavailable")
                    val llm = LlmWrapper.builder()
                        .llmCreateInput(
                            LlmCreateInput(
                                model_path = paths.model_path,
                                config = ModelConfig(nCtx = 4096),
                                runtime_id = "llama_cpp",
                                compute_unit = null
                            )
                        )
                        .build()
                        .getOrThrow()

                    val templated = llm.applyChatTemplate(
                        arrayListOf(ChatMessage("user", userPrompt)),
                        null,
                        false
                    ).getOrThrow()

                    val result = StringBuilder()
                    llm.generateStreamFlow(
                        templated.formattedText,
                        GenerationConfig(maxTokens = 256)
                    ).collect { item ->
                        when (item) {
                            is LlmStreamResult.Token -> {
                                result.append(item.text)
                                runOnUiThread { output.text = result.toString() }
                            }
                            is LlmStreamResult.Completed -> Unit
                            is LlmStreamResult.Error -> error(item.throwable.message ?: "Inference failed")
                        }
                    }
                    result.toString()
                }
                output.text = response
                status.text = "Inference complete · llama_cpp · model: $MODEL_NAME"
            } catch (error: Throwable) {
                status.text = "Runtime error: ${error.message ?: error::class.java.simpleName}"
            } finally {
                runButton.isEnabled = true
            }
        }
    }

    override fun onDestroy() {
        runJob?.cancel()
        uiScope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val MODEL_NAME = "unsloth/Qwen3-0.6B-GGUF"
    }
}
