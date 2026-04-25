import { useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type IoniconsName = React.ComponentProps<typeof Ionicons>["name"];

function TabIcon({ name, focused }: { name: IoniconsName; focused: boolean }) {
  return (
    <Ionicons
      name={focused ? name : (`${name}-outline` as IoniconsName)}
      size={24}
      color={focused ? "#6366f1" : "#71717a"}
    />
  );
}

interface OptionItem {
  icon: IoniconsName;
  label: string;
  description: string;
  route: string;
  color: string;
}

const OPTION_SECTIONS: { title: string; items: OptionItem[] }[] = [
  {
    title: "Content",
    items: [
      {
        icon: "library",
        label: "Knowledge",
        description: "Manage your knowledge base",
        route: "/knowledge",
        color: "#6366f1",
      },
      {
        icon: "archive",
        label: "Assets",
        description: "Browse uploaded files & media",
        route: "/assets",
        color: "#22c55e",
      },
    ],
  },
  {
    title: "AI & Intelligence",
    items: [
      {
        icon: "sparkles",
        label: "Personality",
        description: "Your AI's personality profile",
        route: "/personality",
        color: "#f59e0b",
      },
      {
        icon: "school",
        label: "Self-Learning",
        description: "Autonomous learning status",
        route: "/learning",
        color: "#06b6d4",
      },
      {
        icon: "hardware-chip",
        label: "Model Training",
        description: "Fine-tuning and training jobs",
        route: "/model-training",
        color: "#8b5cf6",
      },
      {
        icon: "server",
        label: "Model Status",
        description: "Active model and provider",
        route: "/model-status",
        color: "#64748b",
      },
    ],
  },
  {
    title: "Access & Security",
    items: [
      {
        icon: "people",
        label: "Family Access",
        description: "Manage family members",
        route: "/family",
        color: "#ec4899",
      },
      {
        icon: "shield-checkmark",
        label: "Security",
        description: "2FA, export and account",
        route: "/security",
        color: "#ef4444",
      },
    ],
  },
];

function OptionsSheet({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  function navigate(route: string) {
    onClose();
    // Small delay so the modal closes before the screen pushes
    setTimeout(() => router.push(route as any), 150);
  }

  return (
    <View className="flex-1 justify-end">
      {/* Scrim */}
      <Pressable className="absolute inset-0 bg-black/60" onPress={onClose} />

      {/* Sheet */}
      <View
        className="bg-zinc-950 rounded-t-3xl border-t border-zinc-800"
        style={{ paddingBottom: insets.bottom + 8 }}
      >
        {/* Handle */}
        <View className="items-center pt-3 pb-2">
          <View className="w-10 h-1 rounded-full bg-zinc-700" />
        </View>

        {/* Title */}
        <View className="flex-row items-center justify-between px-5 pt-1 pb-4">
          <Text className="text-white text-xl font-bold">Options</Text>
          <Pressable onPress={onClose} className="p-1 active:opacity-60">
            <Ionicons name="close" size={22} color="#71717a" />
          </Pressable>
        </View>

        <ScrollView
          showsVerticalScrollIndicator={false}
          style={{ maxHeight: 520 }}
        >
          {OPTION_SECTIONS.map((section, si) => (
            <View key={section.title} className={si > 0 ? "mt-5" : ""}>
              <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-widest px-5 mb-2">
                {section.title}
              </Text>
              <View className="mx-4 bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
                {section.items.map((item, ii) => (
                  <View key={item.route}>
                    {ii > 0 && <View className="h-px bg-zinc-800 ml-14" />}
                    <Pressable
                      onPress={() => navigate(item.route)}
                      className="flex-row items-center gap-3 px-4 py-3.5 active:bg-zinc-800/60"
                    >
                      <View
                        className="w-9 h-9 rounded-xl items-center justify-center"
                        style={{ backgroundColor: item.color + "22" }}
                      >
                        <Ionicons name={item.icon} size={18} color={item.color} />
                      </View>
                      <View className="flex-1">
                        <Text className="text-white font-medium text-sm">{item.label}</Text>
                        <Text className="text-zinc-500 text-xs">{item.description}</Text>
                      </View>
                      <Ionicons name="chevron-forward" size={15} color="#52525b" />
                    </Pressable>
                  </View>
                ))}
              </View>
            </View>
          ))}
          <View className="h-4" />
        </ScrollView>
      </View>
    </View>
  );
}

export default function TabsLayout() {
  const [optionsVisible, setOptionsVisible] = useState(false);

  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: "#09090b",
            borderTopColor: "#27272a",
          },
          tabBarActiveTintColor: "#6366f1",
          tabBarInactiveTintColor: "#71717a",
          tabBarLabelStyle: { fontSize: 12 },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "Chat",
            tabBarIcon: ({ focused }) => (
              <TabIcon name="chatbubbles" focused={focused} />
            ),
          }}
        />
        <Tabs.Screen
          name="options"
          options={{
            title: "Options",
            tabBarIcon: ({ focused }) => (
              <TabIcon name="grid" focused={focused} />
            ),
          }}
          listeners={{
            tabPress: (e) => {
              e.preventDefault();
              setOptionsVisible(true);
            },
          }}
        />
        <Tabs.Screen
          name="settings"
          options={{
            title: "Settings",
            tabBarIcon: ({ focused }) => (
              <TabIcon name="settings" focused={focused} />
            ),
          }}
        />
        {/* Hide the old knowledge tab — it's accessed via Options now */}
        <Tabs.Screen name="knowledge" options={{ href: null }} />
      </Tabs>

      <Modal
        visible={optionsVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setOptionsVisible(false)}
        statusBarTranslucent
      >
        <OptionsSheet onClose={() => setOptionsVisible(false)} />
      </Modal>
    </>
  );
}
