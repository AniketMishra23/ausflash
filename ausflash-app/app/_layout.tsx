// Root navigator — wraps the entire app in a single Stack.
// Only one screen group exists: (tabs), which holds the Feed.
// AusFlash is light-mode only; no dark-theme branching needed.

import { DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated'; // required by expo-router even if not used directly

export default function RootLayout() {
  return (
    <ThemeProvider value={DefaultTheme}>
      <Stack>
        {/* Hide the native header — the Feed screen renders its own */}
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      </Stack>
      <StatusBar style="dark" />
    </ThemeProvider>
  );
}
