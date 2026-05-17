// Tab group layout.
// The tab bar is hidden — AusFlash is a single full-screen Feed.
// The Tabs wrapper is still required by expo-router for the (tabs) folder group.

import { Tabs } from 'expo-router';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: { display: 'none' }, // no visible tab bar
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Feed' }} />
    </Tabs>
  );
}
