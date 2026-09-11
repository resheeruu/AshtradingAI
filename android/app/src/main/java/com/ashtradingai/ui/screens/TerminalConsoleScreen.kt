package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

data class TerminalLine(
    val timestamp: String = "",
    val type: String = "info", // info, command, success, error, warning
    val message: String = ""
)

@Composable
fun TerminalConsoleScreen(
    uiState: AppUiState,
    onExecuteCommand: (String) -> Unit
) {
    var commandInput by remember { mutableStateOf("") }
    val terminalLines = remember { mutableStateListOf<TerminalLine>() }
    val scrollState = rememberLazyListState()

    LaunchedEffect(uiState.terminalCommandResult) {
        uiState.terminalCommandResult?.let { result ->
            terminalLines.add(
                TerminalLine(
                    timestamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date()),
                    type = if (result.status == "ok" || result.status == "started" || result.status == "switched") "success" else "error",
                    message = result.message
                )
            )
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground)
            .padding(16.dp)
    ) {
        SectionHeader("Terminal Console")
        Spacer(modifier = Modifier.height(8.dp))

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(Color(0xFF0D1117))
                .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
                .padding(12.dp),
            state = scrollState,
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            if (terminalLines.isEmpty()) {
                item {
                    Text(
                        text = "AshtradingAI Terminal v1.0",
                        style = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                        color = AccentGreen
                    )
                    Text(
                        text = "Type 'help' for available commands",
                        style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        color = TextMuted
                    )
                }
            }

            items(terminalLines) { line ->
                Row(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "[${line.timestamp}] ",
                        style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        color = TextMuted
                    )
                    Text(
                        text = when (line.type) {
                            "command" -> "> "
                            "success" -> "+ "
                            "error" -> "! "
                            "warning" -> "* "
                            else -> "  "
                        },
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold
                        ),
                        color = when (line.type) {
                            "command" -> AccentBlue
                            "success" -> AccentGreen
                            "error" -> AccentRed
                            "warning" -> AccentYellow
                            else -> TextMuted
                        }
                    )
                    Text(
                        text = line.message,
                        style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        color = when (line.type) {
                            "command" -> TextPrimary
                            "success" -> AccentGreen
                            "error" -> AccentRed
                            "warning" -> AccentYellow
                            else -> TextSecondary
                        }
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = commandInput,
                onValueChange = { commandInput = it },
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(8.dp)),
                placeholder = {
                    Text(
                        "Enter command...",
                        color = TextMuted,
                        fontFamily = FontFamily.Monospace
                    )
                },
                textStyle = LocalTextStyle.current.copy(
                    fontFamily = FontFamily.Monospace,
                    color = TextPrimary
                ),
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(
                    onSend = {
                        if (commandInput.isNotBlank()) {
                            terminalLines.add(
                                TerminalLine(
                                    timestamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date()),
                                    type = "command",
                                    message = commandInput
                                )
                            )
                            onExecuteCommand(commandInput)
                            commandInput = ""
                        }
                    }
                ),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = AccentBlue,
                    unfocusedBorderColor = DarkBorder,
                    cursorColor = AccentBlue
                )
            )

            Spacer(modifier = Modifier.width(8.dp))

            Button(
                onClick = {
                    if (commandInput.isNotBlank()) {
                        terminalLines.add(
                            TerminalLine(
                                timestamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date()),
                                type = "command",
                                message = commandInput
                            )
                        )
                        onExecuteCommand(commandInput)
                        commandInput = ""
                    }
                },
                modifier = Modifier.height(56.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = AccentBlue,
                    contentColor = Color.White
                )
            ) {
                Text("Send", fontFamily = FontFamily.Monospace)
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            QuickCommandButton("status") { commandInput = "status" }
            QuickCommandButton("risk") { commandInput = "risk" }
            QuickCommandButton("positions") { commandInput = "positions" }
            QuickCommandButton("kill") { commandInput = "kill" }
        }
    }
}

@Composable
private fun QuickCommandButton(
    text: String,
    onClick: () -> Unit
) {
    Button(
        onClick = onClick,
        modifier = Modifier.weight(1f),
        colors = ButtonDefaults.buttonColors(
            containerColor = DarkSurface,
            contentColor = AccentBlue
        ),
        shape = RoundedCornerShape(8.dp)
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            color = AccentBlue
        )
    }
}
